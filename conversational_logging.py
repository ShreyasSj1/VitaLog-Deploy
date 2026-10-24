"""
conversational_logging.py — Conversational Food & Workout Logging Service for VitalLog.

Provides natural language intent parsing, catalog matching, AI interpretation with
resilient rule-based fallback, state machine management (PendingLogDraft),
and atomic database persistence.
"""
import os
import re
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple

from extensions import db
from models import (
    FoodItem, Exercise, FoodLog, GymLog, WorkoutSet,
    PendingLogDraft, UserPreference, utc_iso, now_utc, parse_utc_iso
)
from constants import (
    FOOD_DATA, EXERCISE_CATALOG, CARDIO_EXERCISES,
    CARDIO_META, MUSCLE_FACTORS, INTENSITY_MAP
)
from utils import get_today


# ───────────────────────────────────────────────────────────────────────────
# Number and Word Mappings
# ───────────────────────────────────────────────────────────────────────────

WORD_TO_NUM = {
    "a": 1.0, "an": 1.0, "one": 1.0, "two": 2.0, "three": 3.0,
    "four": 4.0, "five": 5.0, "six": 6.0, "seven": 7.0, "eight": 8.0,
    "nine": 9.0, "ten": 10.0, "half": 0.5, "quarter": 0.25,
    "couple": 2.0, "few": 3.0
}

MEAL_CATEGORIES = ["Breakfast", "Lunch", "Dinner", "Snacks", "Pre/Post Workout"]

# ───────────────────────────────────────────────────────────────────────────
# Conversational Commands & Non-Food Filter
# ───────────────────────────────────────────────────────────────────────────

CONFIRMATION_COMMANDS = {
    "log it", "log this", "log meal", "log food", "log workout", "log that",
    "confirm", "confirm and save", "confirm meal", "confirm workout",
    "save it", "save this", "save this meal", "save meal", "save that", "save",
    "looks good", "looks great", "that's correct", "thats correct", "that's right", "thats right",
    "correct", "yes save", "please log", "please add these foods", "please add",
    "add it", "go ahead"
}

CANCELLATION_COMMANDS = {
    "cancel", "cancel this", "cancel that", "cancel draft", "cancel meal", "cancel workout",
    "discard", "discard this", "never mind", "nevermind", "stop", "delete draft",
    "don't log", "dont log"
}

NON_FOOD_TERMS = {
    "log it", "log this", "log that", "log meal", "log food", "log workout", "log", "logged",
    "save it", "save this", "save that", "save this meal", "save meal", "save", "saved",
    "confirm", "confirm and save", "confirm meal", "confirm workout",
    "cancel", "cancel this", "cancel that", "cancel draft", "cancel meal", "discard",
    "never mind", "nevermind", "stop", "delete draft", "delete", "edit", "update", "modify",
    "that's correct", "thats correct", "that's right", "thats right", "correct",
    "looks good", "looks great", "yes", "no", "yeah", "nope", "ok", "okay", "sure",
    "thanks", "thank you", "please", "done", "great", "cool", "hello", "hi", "hey",
    "use standard serving", "use standard servings", "standard serving", "standard servings",
    "what did i eat", "how many calories", "help", "coach", "today", "yesterday",
    "breakfast", "lunch", "dinner", "snack", "snacks", "meal", "food",
}


def is_confirmation_command(text: str) -> bool:
    """Check if message is an explicit confirmation command."""
    clean = re.sub(r"[^\w\s]", "", text).strip().lower()
    if clean in CONFIRMATION_COMMANDS:
        return True
    for cmd in CONFIRMATION_COMMANDS:
        if clean == cmd or clean.startswith(cmd + " ") or clean.endswith(" " + cmd):
            return True
    return False


def is_cancellation_command(text: str) -> bool:
    """Check if message is an explicit cancellation command."""
    clean = re.sub(r"[^\w\s]", "", text).strip().lower()
    if clean in CANCELLATION_COMMANDS:
        return True
    for cmd in CANCELLATION_COMMANDS:
        if clean == cmd or clean.startswith(cmd + " ") or clean.endswith(" " + cmd):
            return True
    return False


def is_valid_food_name(name: str) -> bool:
    """Validate that candidate string represents an actual food item, rejecting commands, verbs, filler."""
    if not name or not isinstance(name, str):
        return False
    clean = re.sub(r"[^\w\s]", "", name).strip().lower()
    if not clean or len(clean) < 2:
        return False
    if clean in NON_FOOD_TERMS:
        return False
    if is_confirmation_command(clean) or is_cancellation_command(clean):
        return False
    for verb in ["log ", "save ", "cancel ", "confirm ", "delete ", "discard "]:
        if clean.startswith(verb):
            return False
    if clean in {"eat", "ate", "eating", "had", "have", "drink", "drank", "drinking", "trained", "workout", "gym", "it", "this", "that"}:
        return False
    return True


# ───────────────────────────────────────────────────────────────────────────
# Catalog Matching & Aliasing
# ───────────────────────────────────────────────────────────────────────────

FOOD_ALIASES = {
    "dosa": "Masala Dosa",
    "plain dosa": "Dosa (Plain)",
    "masala dosa": "Masala Dosa",
    "idli": "Idli",
    "idlis": "Idli",
    "vada": "Vada (Medu)",
    "medu vada": "Vada (Medu)",
    "coffee": "Tea / Coffee",
    "tea": "Tea / Coffee",
    "chai": "Tea / Coffee",
    "black coffee": "Tea / Coffee",
    "rice": "Rice (Cooked)",
    "cooked rice": "Rice (Cooked)",
    "white rice": "Rice (Cooked)",
    "plain rice": "Plain Rice",
    "jeera rice": "Jeera Rice",
    "curd rice": "Curd Rice",
    "chapati": "Chapati",
    "chapatis": "Chapati",
    "roti": "Chapati",
    "rotis": "Chapati",
    "dal": "Dal Tadka",
    "dal tadka": "Dal Tadka",
    "rajma": "Rajma Masala",
    "chana": "Chana Masala",
    "paneer": "Paneer Curry",
    "paneer curry": "Paneer Curry",
    "chicken": "Chicken Curry",
    "chicken curry": "Chicken Curry",
    "chicken biryani": "Chicken Biryani",
    "biryani": "Chicken Biryani",
    "grilled chicken": "Grilled Chicken",
    "chicken breast": "Grilled Chicken",
    "fish curry": "Fish Curry",
    "fish": "Fish Curry",
    "curd": "Curd (Plain)",
    "yogurt": "Greek Yogurt",
    "boiled eggs": "Boiled Eggs",
    "boiled egg": "Boiled Eggs",
    "egg": "Boiled Eggs",
    "eggs": "Boiled Eggs",
    "omelette": "Omelette",
    "egg curry": "Egg Curry",
    "milk": "Milk (200ml)",
    "bread": "Bread (White)",
    "banana": "Banana",
    "bananas": "Banana",
    "protein shake": "Protein Shake (Water)",
    "shake": "Protein Shake (Water)",
    "protein powder": "Protein Shake (Water)",
    "whey": "Protein Shake (Water)",
    "whey protein": "Protein Shake (Water)",
    "scoop of protein": "Protein Shake (Water)",
    "protein bar": "Protein Bar",
    "almonds": "Nuts (Handful)",
    "almond": "Nuts (Handful)",
    "nuts": "Nuts (Handful)",
    "apple": "Fruit Bowl",
    "apples": "Fruit Bowl",
    "fruits": "Fruit Bowl",
    "fruit": "Fruit Bowl",
    "fruit bowl": "Fruit Bowl",
    "pb": "Peanut Butter Sandwich",
    "peanut butter": "Peanut Butter Sandwich",
    "pb sandwich": "Peanut Butter Sandwich",
    "samosa": "Samosa",
    "samosas": "Samosa",
    "burger": "Veg Burger",
    "french fries": "French Fries",
    "fries": "French Fries",
    "salad": "Salad",
    "soup": "Soup (Veg)",
}

EXERCISE_ALIASES = {
    "bench press": ("Bench Press", "Chest"),
    "bench": ("Bench Press", "Chest"),
    "incline bench": ("Incline Bench Press", "Chest"),
    "incline bench press": ("Incline Bench Press", "Chest"),
    "lat pulldown": ("Lat Pulldown", "Back"),
    "lat pulldowns": ("Lat Pulldown", "Back"),
    "lat pull down": ("Lat Pulldown", "Back"),
    "lat pull": ("Lat Pulldown", "Back"),
    "pull ups": ("Pull-Ups", "Back"),
    "pull-ups": ("Pull-Ups", "Back"),
    "pullup": ("Pull-Ups", "Back"),
    "pullups": ("Pull-Ups", "Back"),
    "push ups": ("Push-Ups", "Chest"),
    "push-ups": ("Push-Ups", "Chest"),
    "pushup": ("Push-Ups", "Chest"),
    "pushups": ("Push-Ups", "Chest"),
    "deadlift": ("Deadlift", "Back"),
    "deadlifts": ("Deadlift", "Back"),
    "squat": ("Squat", "Legs"),
    "squats": ("Squat", "Legs"),
    "leg press": ("Leg Press", "Legs"),
    "bicep curl": ("Bicep Curl", "Arms"),
    "bicep curls": ("Bicep Curl", "Arms"),
    "curls": ("Bicep Curl", "Arms"),
    "tricep pushdown": ("Tricep Pushdown", "Arms"),
    "overhead press": ("Overhead Press", "Shoulders"),
    "shoulder press": ("Overhead Press", "Shoulders"),
    "ohp": ("Overhead Press", "Shoulders"),
    "lateral raises": ("Lateral Raises", "Shoulders"),
    "treadmill": ("Treadmill (Running)", "Cardio"),
    "running": ("Treadmill (Running)", "Cardio"),
    "jogging": ("Treadmill (Running)", "Cardio"),
    "cycling": ("Cycling", "Cardio"),
    "cycle": ("Cycling", "Cardio"),
    "elliptical": ("Elliptical", "Cardio"),
    "incline walking": ("Inclined Walking", "Cardio"),
    "inclined walking": ("Inclined Walking", "Cardio"),
    "plank": ("Plank", "Core"),
}


def match_food_item(name: str) -> Optional[Dict[str, Any]]:
    """Match a natural language food string against known catalogs."""
    if not name:
        return None
    clean = name.strip().lower()
    if not clean or not is_valid_food_name(clean):
        return None

    # Check direct alias
    canonical_name = FOOD_ALIASES.get(clean)
    if canonical_name:
        clean = canonical_name.lower()

    # Query DB lookup table first
    food_ref = FoodItem.query.filter(FoodItem.name.ilike(clean)).first()
    if not food_ref and canonical_name:
        food_ref = FoodItem.query.filter(FoodItem.name.ilike(canonical_name)).first()

    if food_ref:
        return {
            "name": food_ref.name,
            "meal_category": food_ref.meal_category,
            "calories": food_ref.calories,
            "protein": food_ref.protein,
            "fat": food_ref.fat,
            "sugar": food_ref.sugar,
            "is_catalog": True,
        }

    # Search in constants.py FOOD_DATA
    for category, items in FOOD_DATA.items():
        for item_name, (cal, pro, fat, sug) in items.items():
            if item_name.lower() == clean or clean in item_name.lower() or item_name.lower() in clean:
                return {
                    "name": item_name,
                    "meal_category": category,
                    "calories": float(cal),
                    "protein": float(pro),
                    "fat": float(fat),
                    "sugar": float(sug),
                    "is_catalog": True,
                }

    return None


def match_exercise(name: str) -> Dict[str, Any]:
    """Match a natural language exercise string against the Exercise catalog."""
    clean = name.strip().lower()

    # Check direct aliases
    if clean in EXERCISE_ALIASES:
        canon_name, muscle = EXERCISE_ALIASES[clean]
        is_cardio = canon_name in CARDIO_EXERCISES
        return {"name": canon_name, "muscle": muscle, "is_cardio": is_cardio, "is_catalog": True}

    # Query DB Exercise table
    ex_ref = Exercise.query.filter(Exercise.name.ilike(clean)).first()
    if ex_ref:
        return {
            "name": ex_ref.name,
            "muscle": ex_ref.muscle_group,
            "is_cardio": ex_ref.is_cardio,
            "is_catalog": True,
        }

    # Search EXERCISE_CATALOG
    for muscle, exercises in EXERCISE_CATALOG.items():
        for ex in exercises:
            if ex.lower() == clean or clean in ex.lower() or ex.lower() in clean:
                return {
                    "name": ex,
                    "muscle": muscle,
                    "is_cardio": ex in CARDIO_EXERCISES,
                    "is_catalog": True,
                }

    # Fallback to unrecognized exercise
    is_cardio = any(w in clean for w in ["run", "walk", "jog", "cycle", "cardio", "treadmill", "elliptical"])
    return {
        "name": name.strip().title(),
        "muscle": "Cardio" if is_cardio else "Other",
        "is_cardio": is_cardio,
        "is_catalog": False,
    }


def infer_meal_category(text: str) -> str:
    """Infer meal category from text or current time of day."""
    lower = text.lower()
    if "breakfast" in lower:
        return "Breakfast"
    if "lunch" in lower:
        return "Lunch"
    if "dinner" in lower:
        return "Dinner"
    if "snack" in lower or "snacks" in lower:
        return "Snacks"
    if "pre-workout" in lower or "post-workout" in lower or "workout" in lower:
        return "Pre/Post Workout"

    # Time-based fallback
    hour = datetime.now().hour
    if 5 <= hour < 11:
        return "Breakfast"
    elif 11 <= hour < 16:
        return "Lunch"
    elif 16 <= hour < 19:
        return "Snacks"
    else:
        return "Dinner"


# ───────────────────────────────────────────────────────────────────────────
# Deterministic Rule-Based Fallback Parser
# ───────────────────────────────────────────────────────────────────────────

def parse_food_rule_based(text: str) -> Dict[str, Any]:
    """Deterministic extractor for food queries with portion detection, scaling, and validation."""
    meal = infer_meal_category(text)
    items = []
    missing_fields = []

    # Strip correction artifacts (Rule E)
    normalized = text.lower()
    normalized = re.sub(
        r"\b(?:not|instead of)\s+(?:\d+(?:\.\d+)?|a|an|one|two|three|four|five|six|seven|eight|nine|ten)\b",
        "",
        normalized
    )

    # Strip conversational prefixes
    for prep in [
        "i had", "i ate", "i consumed", "i drank", "i took", "logged",
        "for breakfast", "for lunch", "for dinner", "for snacks", "for my meal",
        "please log", "please add these foods", "please add", "add", "log"
    ]:
        normalized = re.sub(rf"\b{re.escape(prep)}\b", "", normalized)

    # Split on commas, "and", "with", "plus"
    parts = re.split(r",|\band\b|\bwith\b|\bplus\b", normalized)

    household_units_pattern = (
        r"(?:(a|an|one|two|three|four|five|six|seven|eight|nine|ten|half|quarter|couple|few|\d+(?:\.\d+)?)\s+)?"
        r"(bowl|bowls|plate|plates|cup|cups|handful|handfuls|scoop|scoops|"
        r"glass|glasses|slice|slices|piece|pieces|serving|servings|bottle|bottles)(?:\s+of)?\b"
    )

    raw_parsed_items = []

    for part in parts:
        segment = part.strip()
        if not segment:
            continue

        qty = 1.0
        has_qty = False
        serving_desc = ""
        food_candidate = ""

        # Check 1: Volume in ml / liters (e.g. "250 ml milk", "1l water")
        vol_match = re.search(r"(\d+(?:\.\d+)?)\s*(ml|milliliters?|millilitres?|l|liters?|litres?)\b", segment)
        # Check 2: Weight in g / kg (e.g. "150 g chicken", "150g grilled chicken")
        wt_match = re.search(r"(\d+(?:\.\d+)?)\s*(g|gm|gms|grams?|kg|kgs|kilograms?)\b", segment)
        # Check 3: Household units (e.g. "1 bowl of dal", "a plate of rice", "one scoop of protein powder")
        hh_match = re.search(household_units_pattern, segment)

        if vol_match:
            val = float(vol_match.group(1))
            unit = vol_match.group(2).lower()
            ml = val * 1000.0 if unit.startswith("l") else val
            has_qty = True
            remaining = segment[:vol_match.start()] + " " + segment[vol_match.end():]
            food_candidate = re.sub(r"^(?:of|a|an|the|some)\s+", "", remaining.strip()).strip()

            # Milk (200ml) is base 200ml
            qty = round(ml / 200.0, 2)
            disp_ml = int(ml) if ml.is_integer() else ml
            serving_desc = f"{disp_ml} ml"

        elif wt_match:
            val = float(wt_match.group(1))
            unit = wt_match.group(2).lower()
            grams = val * 1000.0 if unit.startswith("k") else val
            has_qty = True
            remaining = segment[:wt_match.start()] + " " + segment[wt_match.end():]
            food_candidate = re.sub(r"^(?:of|a|an|the|some)\s+", "", remaining.strip()).strip()

            # Chicken (100g base)
            if "chicken" in food_candidate:
                qty = round(grams / 100.0, 2)
                if food_candidate == "chicken":
                    food_candidate = "grilled chicken"
            else:
                qty = round(grams / 100.0, 2)
            disp_g = int(grams) if grams.is_integer() else grams
            serving_desc = f"{disp_g} g"

        elif hh_match:
            num_token = (hh_match.group(1) or "1").lower()
            unit_token = hh_match.group(2).lower()
            qty = WORD_TO_NUM.get(num_token, 1.0)
            if re.match(r"^\d+(?:\.\d+)?$", num_token):
                qty = float(num_token)
            has_qty = True
            remaining = segment[:hh_match.start()] + " " + segment[hh_match.end():]
            food_candidate = re.sub(r"^(?:of|a|an|the|some)\s+", "", remaining.strip()).strip()
            serving_desc = f"{int(qty) if qty.is_integer() else qty} {unit_token}"

        else:
            # Check 4: Counts (e.g. "2 boiled eggs", "3 chapatis", "1 dosa")
            tokens = segment.split()
            food_tokens = []
            for token in tokens:
                if token in WORD_TO_NUM and not has_qty:
                    qty = WORD_TO_NUM[token]
                    has_qty = True
                elif re.match(r"^\d+(?:\.\d+)?$", token) and not has_qty:
                    qty = float(token)
                    has_qty = True
                elif re.match(r"^(?:servings?|pieces?|slices?)$", token):
                    has_qty = True
                else:
                    food_tokens.append(token)

            food_candidate = " ".join(food_tokens).strip()
            food_candidate = re.sub(r"^(?:of|a|an|the|some)\s+", "", food_candidate).strip()
            if has_qty:
                serving_desc = f"{int(qty) if qty.is_integer() else qty} serving{'s' if qty != 1 else ''}"
            else:
                qty = 1.0
                has_qty = False
                serving_desc = "1 serving"

        # Final cleanup and validation of candidate string
        food_candidate = re.sub(r"^(?:of|a|an|the|some)\s+", "", food_candidate).strip()
        if not is_valid_food_name(food_candidate):
            continue

        raw_parsed_items.append({
            "candidate": food_candidate,
            "qty": qty,
            "has_qty": has_qty,
            "serving_desc": serving_desc,
        })

    if not raw_parsed_items:
        return {
            "intent": "food_log",
            "meal": meal,
            "meal_category": meal,
            "date": get_today().isoformat(),
            "items": [],
            "missing_fields": [],
            "totals": {"calories": 0.0, "protein": 0.0, "fat": 0.0, "sugar": 0.0}
        }

    # Rule D vs Rule C enforcement:
    num_with_qty = sum(1 for it in raw_parsed_items if it["has_qty"])
    num_without_qty = sum(1 for it in raw_parsed_items if not it["has_qty"])

    for raw in raw_parsed_items:
        fc = raw["candidate"]
        qty = raw["qty"]
        has_qty = raw["has_qty"]
        serving_desc = raw["serving_desc"]

        matched = match_food_item(fc)

        # Rule D: If at least one item has explicit quantity and this one does not,
        # apply disclosed standard serving so confirmation is not blocked!
        if not has_qty and num_with_qty > 0:
            has_qty = True
            qty = 1.0
            if matched and any(w in matched["name"].lower() for w in ["dal", "sambar", "rasam", "curd", "soup"]):
                serving_desc = "1 bowl (standard estimate)"
            elif matched and "rice" in matched["name"].lower():
                serving_desc = "1 plate (standard estimate)"
            else:
                serving_desc = "1 serving (standard estimate)"

        if matched:
            items.append({
                "food": matched["name"],
                "meal_category": matched.get("meal_category") or meal,
                "qty": qty,
                "has_quantity": has_qty,
                "calories": round(matched["calories"] * qty, 1),
                "protein": round(matched["protein"] * qty, 1),
                "fat": round(matched["fat"] * qty, 1),
                "sugar": round(matched["sugar"] * qty, 1),
                "provenance": "catalog",
                "is_estimate": False,
                "serving_desc": serving_desc or f"{qty} serving{'s' if qty != 1 else ''}"
            })
            if not has_qty:
                missing_fields.append(f"portion for {matched['name']}")
        else:
            est_cal = 200.0 * qty
            est_pro = 6.0 * qty
            est_fat = 5.0 * qty
            est_sug = 2.0 * qty
            items.append({
                "food": fc.title(),
                "meal_category": meal,
                "qty": qty,
                "has_quantity": has_qty,
                "calories": round(est_cal, 1),
                "protein": round(est_pro, 1),
                "fat": round(est_fat, 1),
                "sugar": round(est_sug, 1),
                "provenance": "ai_estimate",
                "is_estimate": True,
                "serving_desc": serving_desc or f"{qty} serving (Estimated)"
            })
            if not has_qty:
                missing_fields.append(f"portion for {fc.title()}")

    # Rule C: Genuinely ambiguous input with 0 items having quantity
    if num_with_qty == 0 and num_without_qty > 0:
        if not missing_fields:
            missing_fields = ["portion sizes"]

    return {
        "intent": "food_log",
        "meal": meal,
        "meal_category": meal,
        "date": get_today().isoformat(),
        "items": items,
        "missing_fields": missing_fields,
        "totals": {
            "calories": round(sum(i["calories"] for i in items), 1),
            "protein": round(sum(i["protein"] for i in items), 1),
            "fat": round(sum(i["fat"] for i in items), 1),
            "sugar": round(sum(i["sugar"] for i in items), 1),
        }
    }


def parse_workout_rule_based(text: str, user_weight: Optional[float] = None) -> Dict[str, Any]:
    """Deterministic extractor for workout queries when LLM is unavailable."""
    exercises = []
    missing_fields = []
    body_weight = user_weight if user_weight and user_weight > 0 else 70.0

    # 1. Cardio detection: e.g. "treadmill for 25 minutes at 5 km/h and 8% incline" or "with incline 6"
    cardio_match = re.search(
        r"(treadmill|running|cycling|elliptical|walking|inclined walking)"
        r".*?(\d+(?:\.\d+)?)\s*(?:min|mins|minutes)"
        r"(?:.*?(\d+(?:\.\d+)?)\s*(?:km/h|kph|mph|speed))?"
        r"(?:.*?(?:incline\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*%\s*(?:incline)?))?",
        text,
        re.IGNORECASE
    )
    if cardio_match:
        c_name = cardio_match.group(1).lower()
        duration = float(cardio_match.group(2))
        speed = float(cardio_match.group(3)) if cardio_match.group(3) else 0.0
        incline = float(cardio_match.group(4) or cardio_match.group(5)) if (cardio_match.group(4) or cardio_match.group(5)) else 0.0

        matched_c = match_exercise(c_name)
        canon_name = matched_c["name"]
        meta = CARDIO_META.get(canon_name, {"met": 5.0, "baseline_speed": 6.0, "speed_factor": 0.25})
        base_met = meta["met"]
        baseline_speed = meta["baseline_speed"]
        speed_factor_val = meta["speed_factor"]
        speed_boost = max(0, speed - baseline_speed) * speed_factor_val
        incline_boost = max(0, incline) * 0.35 if canon_name == "Inclined Walking" else 0
        cals = round(((base_met + speed_boost + incline_boost) * 3.5 * body_weight / 200) * duration, 1)

        exercises.append({
            "exercise": canon_name,
            "muscle": "Cardio",
            "is_cardio": True,
            "duration": duration,
            "speed": speed,
            "incline": incline,
            "intensity": "Medium",
            "sets": 1,
            "reps": 0,
            "weight": 0.0,
            "calories": cals,
            "sets_detail": [],
        })
        return {
            "intent": "workout_log",
            "date": get_today().isoformat(),
            "exercises": exercises,
            "missing_fields": [],
        }

    # 2. Strength exercises detection: e.g. "bench press at 60 kg for 3 sets of 8, then lat pulldowns at 40 kg for 3 sets of 10"
    segments = re.split(r",|\bthen\b|\band\b", text, flags=re.IGNORECASE)
    for seg in segments:
        s = seg.strip()
        if not s:
            continue

        # Look for pattern: <exercise> at <weight> kg for <sets> sets of <reps>
        m1 = re.search(r"([a-zA-Z\s\-]+?)\s+(?:at|@)\s*(\d+(?:\.\d+)?)\s*(?:kg|lbs)?\s*(?:for\s*)?(\d+)\s*sets?\s*(?:of|x)\s*(\d+)", s, re.IGNORECASE)
        # Look for pattern: <exercise> <weight> kg for <sets>x<reps>
        m2 = re.search(r"([a-zA-Z\s\-]+?)\s+(\d+(?:\.\d+)?)\s*(?:kg|lbs)?\s*(?:for\s*)?(\d+)\s*(?:x|sets?\s*of)\s*(\d+)", s, re.IGNORECASE)
        # Look for pattern: <exercise> <sets> sets of <reps> at <weight> kg
        m3 = re.search(r"([a-zA-Z\s\-]+?)\s+(\d+)\s*sets?\s*(?:of|x)\s*(\d+)\s*(?:reps?)?\s*(?:at|@)\s*(\d+(?:\.\d+)?)\s*(?:kg|lbs)?", s, re.IGNORECASE)
        # Look for bodyweight pattern: <exercise> <sets> sets of <reps> (e.g. push-ups 3 sets of 15)
        m4 = re.search(r"([a-zA-Z\s\-]+?)\s+(\d+)\s*sets?\s*(?:of|x)\s*(\d+)\s*(?:reps?)?", s, re.IGNORECASE)

        ex_name, weight, sets_count, reps_count = None, 0.0, 0, 0
        if m1:
            ex_name = m1.group(1).strip()
            weight = float(m1.group(2))
            sets_count = int(m1.group(3))
            reps_count = int(m1.group(4))
        elif m2:
            ex_name = m2.group(1).strip()
            weight = float(m2.group(2))
            sets_count = int(m2.group(3))
            reps_count = int(m2.group(4))
        elif m3:
            ex_name = m3.group(1).strip()
            sets_count = int(m3.group(2))
            reps_count = int(m3.group(3))
            weight = float(m3.group(4))
        elif m4:
            ex_name = m4.group(1).strip()
            sets_count = int(m4.group(2))
            reps_count = int(m4.group(3))
            weight = 0.0

        if ex_name and sets_count > 0 and reps_count > 0:
            matched_ex = match_exercise(ex_name)
            muscle = matched_ex["muscle"]
            m_factor = MUSCLE_FACTORS.get(muscle, 1.0)
            eff_weight = weight if weight > 0 else 50.0
            cals = round((sets_count * reps_count * eff_weight * 0.04) * m_factor * 1.0, 1)

            sets_detail = [
                {"set_number": i, "reps": reps_count, "weight": weight}
                for i in range(1, sets_count + 1)
            ]
            exercises.append({
                "exercise": matched_ex["name"],
                "muscle": muscle,
                "is_cardio": False,
                "sets": sets_count,
                "reps": reps_count * sets_count,
                "weight": weight,
                "intensity": "Medium",
                "duration": 0.0,
                "speed": 0.0,
                "incline": 0.0,
                "calories": cals,
                "sets_detail": sets_detail,
            })

    if not exercises:
        # Check if incomplete workout was mentioned (e.g. "I did chest and triceps today")
        workout_keywords = ["workout", "trained", "gym", "chest", "back", "legs", "shoulders", "arms", "triceps", "biceps"]
        if any(w in text.lower() for w in workout_keywords):
            missing_fields.append("specific exercises, sets, reps, and weights")

    return {
        "intent": "workout_log",
        "date": get_today().isoformat(),
        "exercises": exercises,
        "missing_fields": missing_fields,
    }


# ───────────────────────────────────────────────────────────────────────────
# AI Interpretation Layer (Groq with Schema / JSON constraints)
# ───────────────────────────────────────────────────────────────────────────

def call_groq_interpretation(message: str, active_draft_data: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
    """Query Groq to parse conversational logging intent with strict JSON structure."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        preferred_model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")

        system_instruction = (
            "You are VitalLog's structured fitness logging interpreter. Analyze the user's message.\n"
            "Respond ONLY with a valid JSON object with the following schema:\n"
            "{\n"
            '  "intent": "food_log" | "workout_log" | "draft_action" | "general_chat",\n'
            '  "action": "confirm" | "cancel" | "edit" | null,\n'
            '  "meal_category": "Breakfast" | "Lunch" | "Dinner" | "Snacks" | "Pre/Post Workout" | null,\n'
            '  "food_items": [\n'
            '     {"name": "...", "quantity": 1.0, "unit": "serving", "has_quantity": true, "calories": 0, "protein": 0, "fat": 0, "sugar": 0, "is_ai_estimate": false}\n'
            '  ],\n'
            '  "workout_exercises": [\n'
            '     {"exercise": "...", "sets": 3, "reps": 10, "weight": 60.0, "is_cardio": false, "duration": 0, "speed": 0, "incline": 0, "sets_detail": []}\n'
            '  ],\n'
            '  "missing_fields": ["..."],\n'
            '  "clarification_question": "..."\n'
            "}\n"
            "Rules:\n"
            "- If user asks about diet advice, motivation, or questions without logging intent, set intent: 'general_chat'.\n"
            "- If user says 'confirm', 'save it', 'looks good', set intent: 'draft_action', action: 'confirm'.\n"
            "- If user says 'cancel', 'discard', set intent: 'draft_action', action: 'cancel'.\n"
            "- Do not invent exact quantities if missing; list missing fields.\n"
            "- If food is homemade or not typical catalog, provide reasonable estimated calories and macros and set is_ai_estimate: true."
        )

        messages = [
            {"role": "system", "content": system_instruction},
        ]
        if active_draft_data:
            messages.append({"role": "system", "content": f"Active draft context: {json.dumps(active_draft_data)}"})
        messages.append({"role": "user", "content": message})

        completion = client.chat.completions.create(
            messages=messages,
            model=preferred_model,
            temperature=0.1,
            max_tokens=600,
            response_format={"type": "json_object"} if "gpt" in preferred_model else None
        )
        if completion and completion.choices:
            raw = completion.choices[0].message.content
            # Extract JSON block if wrapped
            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
    except Exception as e:
        print(f"[ConversationalLogger] Groq extraction fallback: {e}")

    return None


# ───────────────────────────────────────────────────────────────────────────
# Conversational Logging Controller & State Machine
# ───────────────────────────────────────────────────────────────────────────

def apply_standard_servings_to_draft(draft: PendingLogDraft) -> Dict[str, Any]:
    """Apply default standard servings to all unresolved items in a pending food draft."""
    data = draft.get_data()
    items = data.get("items", [])
    for it in items:
        it["has_quantity"] = True
        if not it.get("qty") or it.get("qty") <= 0:
            it["qty"] = 1.0
        desc = it.get("serving_desc", "")
        if "standard estimate" not in desc and "standard serving" not in desc:
            it["serving_desc"] = f"{it.get('qty', 1.0)} serving (standard estimate)"

    data["totals"] = {
        "calories": round(sum(i.get("calories", 0.0) for i in items), 1),
        "protein": round(sum(i.get("protein", 0.0) for i in items), 1),
        "fat": round(sum(i.get("fat", 0.0) for i in items), 1),
        "sugar": round(sum(i.get("sugar", 0.0) for i in items), 1),
    }
    data["missing_fields"] = []
    draft.set_data(data)
    draft.missing_fields = json.dumps([])
    draft.clarification_prompt = None
    draft.state = "awaiting_confirmation"
    draft.touch()
    db.session.commit()

    meal = data.get("meal", "meal")
    draft_dict = draft.to_dict()
    draft_dict["actions"] = ["confirm", "edit", "cancel"]
    return {
        "reply": f"Applied standard servings to your **{meal}** draft. Review below and confirm to save:",
        "draft": draft_dict,
    }


def handle_beverage_sugar_update(draft: PendingLogDraft) -> Optional[Dict[str, Any]]:
    """Handle sugar removal from coffee/tea in an active draft (Rule E)."""
    data = draft.get_data()
    items = data.get("items", [])
    updated = False
    for it in items:
        if any(w in it.get("food", "").lower() for w in ["coffee", "tea", "chai"]):
            old_sugar = it.get("sugar", 7.0 * it.get("qty", 1.0))
            it["sugar"] = 0.0
            sugar_cals = round(old_sugar * 4.0, 1)
            it["calories"] = max(0.0, round(it.get("calories", 90.0) - sugar_cals, 1))
            it["serving_desc"] = f"{it.get('qty', 1.0)} serving (No sugar)"
            updated = True

    if updated:
        data["totals"] = {
            "calories": round(sum(i.get("calories", 0.0) for i in items), 1),
            "protein": round(sum(i.get("protein", 0.0) for i in items), 1),
            "fat": round(sum(i.get("fat", 0.0) for i in items), 1),
            "sugar": round(sum(i.get("sugar", 0.0) for i in items), 1),
        }
        draft.set_data(data)
        draft.touch()
        db.session.commit()
        draft_dict = draft.to_dict()
        draft_dict["actions"] = ["confirm", "edit", "cancel"]
        return {
            "reply": "Updated! Removed sugar from your coffee. Review the updated draft below:",
            "draft": draft_dict,
        }
    return None


def process_conversational_message(user_id: int, message: str) -> Dict[str, Any]:
    """Process an incoming user chat message through conversational logging state machine."""
    clean_msg = message.strip()

    # Retrieve any active draft for this user
    active_draft = PendingLogDraft.query.filter(
        PendingLogDraft.user_id == user_id,
        PendingLogDraft.state.in_(["collecting", "awaiting_confirmation"])
    ).first()

    # Expire draft if past TTL
    if active_draft and active_draft.is_expired():
        active_draft.state = "expired"
        db.session.commit()
        active_draft = None

    lower_msg = clean_msg.lower().strip()
    clean_alpha = re.sub(r"[^\w\s]", "", lower_msg).strip()

    # Step 1: Check explicit confirmation actions FIRST
    if is_confirmation_command(clean_alpha):
        if not active_draft:
            return {
                "reply": "There is no pending meal or workout draft right now. What did you eat or train today?",
                "draft": None
            }
        if active_draft.state == "awaiting_confirmation":
            return confirm_draft(active_draft.draft_id, user_id)
        elif active_draft.state == "collecting":
            if active_draft.log_type == "food":
                apply_standard_servings_to_draft(active_draft)
            return confirm_draft(active_draft.draft_id, user_id)

    # Step 2: Check explicit cancellation actions FIRST
    if is_cancellation_command(clean_alpha):
        if not active_draft:
            return {
                "reply": "There is no pending meal or workout draft right now. What did you eat or train today?",
                "draft": None
            }
        return cancel_draft(active_draft.draft_id, user_id)

    # Step 3: Check standard serving instruction for active food draft (Rule E)
    std_serving_phrases = [
        "use standard serving", "use standard servings", "standard serving", "standard servings",
        "use one standard serving", "the quantity i gave earlier was correct",
        "quantity was correct", "default serving", "use defaults"
    ]
    if active_draft and active_draft.log_type == "food" and any(p in lower_msg for p in std_serving_phrases):
        return apply_standard_servings_to_draft(active_draft)

    # Step 4: Check coffee/tea sugar update (Rule E)
    no_sugar_patterns = ["no sugar", "without sugar", "zero sugar", "0 sugar", "sugar free", "sugar-free", "had no sugar"]
    if active_draft and active_draft.log_type == "food" and any(p in lower_msg for p in no_sugar_patterns):
        sugar_res = handle_beverage_sugar_update(active_draft)
        if sugar_res:
            return sugar_res

    # Step 5: Try AI interpretation first, then fallback to deterministic parser
    active_data = active_draft.get_data() if active_draft else None
    ai_parsed = call_groq_interpretation(clean_msg, active_data)

    intent = "general_chat"
    if ai_parsed and ai_parsed.get("intent") in ["food_log", "workout_log", "draft_action"]:
        intent = ai_parsed.get("intent")
    else:
        # Check rule-based intent
        food_kw = [
            "ate", "had", "eat", "dosa", "rice", "idli", "coffee", "tea", "roti",
            "chapati", "chicken", "salad", "breakfast", "lunch", "dinner", "snack",
            "eggs", "egg", "dal", "milk", "bread", "almonds", "protein", "samosa"
        ]
        workout_kw = [
            "bench press", "squat", "deadlift", "push-ups", "pull-ups", "lat pulldown",
            "treadmill", "running", "sets", "reps", "workout", "trained", "gym"
        ]

        has_food = any(w in lower_msg for w in food_kw)
        has_workout = any(w in lower_msg for w in workout_kw)

        if has_food and has_workout:
            # Multi-intent conflict: Ask user which to log first
            return {
                "reply": "I noticed you mentioned both food and a workout! Which one would you like to log first — your meal or your training session?",
                "draft": None
            }
        elif has_food:
            intent = "food_log"
        elif has_workout:
            intent = "workout_log"
        elif active_draft and active_draft.state == "collecting":
            question_starters = ["how", "what", "why", "when", "can you", "could you", "tell me", "explain", "tips", "suggest", "where", "who"]
            is_question = lower_msg.endswith("?") or any(lower_msg.startswith(w) for w in question_starters)
            if not is_question:
                intent = f"{active_draft.log_type}_log"

    # Step 6: Handle Food Intent
    if intent == "food_log":
        return handle_food_intent(user_id, clean_msg, active_draft, ai_parsed)

    # Step 7: Handle Workout Intent
    if intent == "workout_log":
        return handle_workout_intent(user_id, clean_msg, active_draft, ai_parsed)

    # General chat fallback
    return {"reply": None, "draft": None}


# ───────────────────────────────────────────────────────────────────────────
# Food Intent Handler
# ───────────────────────────────────────────────────────────────────────────

def handle_food_intent(user_id: int, message: str, active_draft: Optional[PendingLogDraft], ai_parsed: Optional[Dict]) -> Dict[str, Any]:
    """Build or update a food log draft."""
    extracted = None
    if ai_parsed and ai_parsed.get("food_items"):
        meal = ai_parsed.get("meal_category") or infer_meal_category(message)
        items = []
        missing = []
        for fi in ai_parsed.get("food_items", []):
            name = fi.get("name", "").strip()
            if not is_valid_food_name(name):
                continue
            qty = float(fi.get("quantity") or 1.0)
            has_qty = bool(fi.get("has_quantity", True))
            matched = match_food_item(name)
            if matched:
                items.append({
                    "food": matched["name"],
                    "meal_category": meal,
                    "qty": qty,
                    "has_quantity": has_qty,
                    "calories": round(matched["calories"] * qty, 1),
                    "protein": round(matched["protein"] * qty, 1),
                    "fat": round(matched["fat"] * qty, 1),
                    "sugar": round(matched["sugar"] * qty, 1),
                    "provenance": "catalog",
                    "is_estimate": False,
                    "serving_desc": f"{qty} serving{'s' if qty != 1 else ''}"
                })
            else:
                cals = float(fi.get("calories") or 200.0 * qty)
                pro = float(fi.get("protein") or 6.0 * qty)
                fat = float(fi.get("fat") or 5.0 * qty)
                sug = float(fi.get("sugar") or 2.0 * qty)
                items.append({
                    "food": name.title(),
                    "meal_category": meal,
                    "qty": qty,
                    "has_quantity": has_qty,
                    "calories": round(cals, 1),
                    "protein": round(pro, 1),
                    "fat": round(fat, 1),
                    "sugar": round(sug, 1),
                    "provenance": "ai_estimate",
                    "is_estimate": True,
                    "serving_desc": f"{qty} serving (Estimated)"
                })
            if not has_qty:
                missing.append(f"portion for {name}")

        extracted = {
            "intent": "food_log",
            "meal": meal,
            "date": get_today().isoformat(),
            "items": items,
            "missing_fields": missing,
        }
    else:
        extracted = parse_food_rule_based(message)

    # Check for corrections if active food draft already exists
    if active_draft and active_draft.log_type == "food":
        existing_data = active_draft.get_data()
        existing_items = existing_data.get("items", [])

        # Filter out any non-food items
        valid_new_items = [it for it in extracted.get("items", []) if is_valid_food_name(it["food"])]

        if valid_new_items:
            for new_item in valid_new_items:
                replaced = False
                for ex_item in existing_items:
                    ex_name = ex_item["food"].lower()
                    new_name = new_item["food"].lower()
                    if ex_name == new_name or ex_name in new_name or new_name in ex_name:
                        ex_item["qty"] = new_item["qty"]
                        ex_item["has_quantity"] = True
                        ex_item["calories"] = round(new_item["calories"], 1)
                        ex_item["protein"] = round(new_item["protein"], 1)
                        ex_item["fat"] = round(new_item["fat"], 1)
                        ex_item["sugar"] = round(new_item["sugar"], 1)
                        ex_item["serving_desc"] = new_item.get("serving_desc", f"{new_item['qty']} serving")
                        replaced = True
                        break
                if not replaced:
                    existing_items.append(new_item)
            extracted["items"] = existing_items

    # Compute totals
    totals = {
        "calories": round(sum(i["calories"] for i in extracted["items"]), 1),
        "protein": round(sum(i["protein"] for i in extracted["items"]), 1),
        "fat": round(sum(i["fat"] for i in extracted["items"]), 1),
        "sugar": round(sum(i["sugar"] for i in extracted["items"]), 1),
    }
    extracted["totals"] = totals

    missing_fields = extracted.get("missing_fields", [])
    has_missing_portions = any(not i.get("has_quantity", True) for i in extracted["items"])
    if has_missing_portions:
        if not missing_fields:
            missing_fields = ["portion sizes"]
    else:
        missing_fields = []
    extracted["missing_fields"] = missing_fields

    # Determine state
    if not extracted["items"]:
        return {
            "reply": "I couldn't identify the specific food items. Could you let me know what you ate and roughly how much?",
            "draft": None
        }

    if missing_fields:
        state = "collecting"
        item_names = [i["food"] for i in extracted["items"] if not i.get("has_quantity", True)]
        if not item_names:
            item_names = [i["food"] for i in extracted["items"]]
        reply = (
            f"Roughly how much {', '.join(item_names)} did you have? "
            "(e.g., 1 plate of rice, 150g chicken, or reply 'use standard serving')"
        )
        prompt = reply
    else:
        state = "awaiting_confirmation"
        meal_name = extracted.get("meal", "Meal")
        reply = f"Here is your **{meal_name}** draft. Review the details below and confirm when you're ready:"
        prompt = None

    # Persist draft state
    if not active_draft or active_draft.log_type != "food":
        # Cancel any previous non-food draft
        if active_draft:
            active_draft.state = "cancelled"
        active_draft = PendingLogDraft(
            draft_id=uuid.uuid4().hex[:16],
            user_id=user_id,
            log_type="food",
            state=state,
            draft_data=json.dumps(extracted),
            missing_fields=json.dumps(missing_fields),
            clarification_prompt=prompt,
        )
        db.session.add(active_draft)
    else:
        active_draft.state = state
        active_draft.set_data(extracted)
        active_draft.missing_fields = json.dumps(missing_fields)
        active_draft.clarification_prompt = prompt
        active_draft.touch()

    db.session.commit()

    draft_dict = active_draft.to_dict()
    draft_dict["actions"] = ["confirm", "edit", "cancel"] if state == "awaiting_confirmation" else ["cancel"]
    return {
        "reply": reply,
        "draft": draft_dict,
    }


# ───────────────────────────────────────────────────────────────────────────
# Workout Intent Handler
# ───────────────────────────────────────────────────────────────────────────

def handle_workout_intent(user_id: int, message: str, active_draft: Optional[PendingLogDraft], ai_parsed: Optional[Dict]) -> Dict[str, Any]:
    """Build or update a workout log draft."""
    from models import User
    user = db.session.get(User, user_id)
    user_weight = user.weight if user and user.weight else 70.0

    extracted = parse_workout_rule_based(message, user_weight)

    # Incomplete workout check (e.g. "I did chest and triceps today")
    if not extracted.get("exercises"):
        reply = (
            "Nice workout! Which specific exercises did you complete? "
            "You can tell me the exercises, sets, reps, and weights (e.g. 'Bench press 3 sets of 8 at 60kg'), "
            "or cardio details like duration and speed."
        )
        if not active_draft or active_draft.log_type != "workout":
            active_draft = PendingLogDraft(
                draft_id=uuid.uuid4().hex[:16],
                user_id=user_id,
                log_type="workout",
                state="collecting",
                draft_data=json.dumps({"intent": "workout_log", "exercises": []}),
                missing_fields=json.dumps(["specific exercises, sets, and reps"]),
                clarification_prompt=reply,
            )
            db.session.add(active_draft)
            db.session.commit()
        return {
            "reply": reply,
            "draft": active_draft.to_dict()
        }

    # If active draft existed, append or update
    if active_draft and active_draft.log_type == "workout":
        existing_data = active_draft.get_data()
        existing_exs = existing_data.get("exercises", [])
        for new_ex in extracted["exercises"]:
            replaced = False
            for ex in existing_exs:
                if ex["exercise"].lower() == new_ex["exercise"].lower():
                    ex.update(new_ex)
                    replaced = True
                    break
            if not replaced:
                existing_exs.append(new_ex)
        extracted["exercises"] = existing_exs

    total_cal = round(sum(e.get("calories", 0.0) for e in extracted["exercises"]), 1)
    extracted["total_estimated_calories"] = total_cal

    state = "awaiting_confirmation"
    reply = "Here is your workout summary ready for review. Check the details and confirm to save:"

    if not active_draft or active_draft.log_type != "workout":
        active_draft = PendingLogDraft(
            draft_id=uuid.uuid4().hex[:16],
            user_id=user_id,
            log_type="workout",
            state=state,
            draft_data=json.dumps(extracted),
            missing_fields=json.dumps([]),
            clarification_prompt=None,
        )
        db.session.add(active_draft)
    else:
        active_draft.state = state
        active_draft.set_data(extracted)
        active_draft.missing_fields = json.dumps([])
        active_draft.clarification_prompt = None
        active_draft.touch()

    db.session.commit()

    draft_dict = active_draft.to_dict()
    draft_dict["actions"] = ["confirm", "edit", "cancel"]
    return {
        "reply": reply,
        "draft": draft_dict,
    }


# ───────────────────────────────────────────────────────────────────────────
# Draft Action Handlers (Confirm, Cancel, Edit)
# ───────────────────────────────────────────────────────────────────────────

def confirm_draft(draft_id: str, user_id: int) -> Dict[str, Any]:
    """Atomically commit draft to the database and transition state to confirmed."""
    draft = PendingLogDraft.query.filter_by(draft_id=draft_id, user_id=user_id).first()
    if not draft:
        return {"success": False, "error": "Draft not found or unauthorized.", "code": 404}

    # Idempotency check: if already confirmed, return success without re-creating records
    if draft.state == "confirmed":
        return {
            "success": True,
            "message": "Draft was already saved.",
            "reply": "This draft was already saved to your logs.",
            "already_confirmed": True,
            "draft": draft.to_dict()
        }

    if draft.is_expired():
        draft.state = "expired"
        db.session.commit()
        return {
            "success": False,
            "error": "Draft has expired. Please describe your log again.",
            "reply": "This draft has expired. Please describe what you ate or trained again.",
            "code": 410
        }

    data = draft.get_data()
    post_date = data.get("date") or get_today().isoformat()

    try:
        if draft.log_type == "food":
            items = data.get("items", [])
            if not items:
                return {
                    "success": False,
                    "error": "Draft contains no items to save.",
                    "reply": "The draft contains no items to save.",
                    "code": 400
                }

            saved_items = []
            for item in items:
                fl = FoodLog(
                    user_id=user_id,
                    date=post_date,
                    meal=item.get("meal_category") or data.get("meal", "Breakfast"),
                    food=item["food"],
                    qty=float(item.get("qty", 1.0)),
                    calories=float(item.get("calories", 0.0)),
                    protein=float(item.get("protein", 0.0)),
                    fat=float(item.get("fat", 0.0)),
                    sugar=float(item.get("sugar", 0.0)),
                    provenance=item.get("provenance", "catalog")
                )
                db.session.add(fl)
                saved_items.append(item["food"])

            draft.state = "confirmed"
            db.session.commit()
            return {
                "success": True,
                "message": f"Successfully logged {len(saved_items)} item(s) for {data.get('meal', 'your meal')}!",
                "reply": f"✅ All set! I've saved {len(saved_items)} item(s) to your food log for {data.get('meal', 'your meal')}.",
                "saved_items": saved_items,
                "draft": draft.to_dict()
            }

        elif draft.log_type == "workout":
            exercises = data.get("exercises", [])
            if not exercises:
                return {
                    "success": False,
                    "error": "Draft contains no exercises to save.",
                    "reply": "The draft contains no exercises to save.",
                    "code": 400
                }

            saved_exercises = []
            for ex in exercises:
                gl = GymLog(
                    user_id=user_id,
                    date=post_date,
                    muscle=ex.get("muscle", "Other"),
                    exercise=ex["exercise"],
                    sets=int(ex.get("sets", 1)),
                    reps=int(ex.get("reps", 0)),
                    weight=float(ex.get("weight", 0.0)),
                    speed=float(ex.get("speed", 0.0)),
                    incline=float(ex.get("incline", 0.0)),
                    intensity=ex.get("intensity", "Medium"),
                    duration=float(ex.get("duration", 0.0)),
                    calories=float(ex.get("calories", 0.0))
                )
                db.session.add(gl)
                db.session.flush()

                # Add sets detail if present
                for s in ex.get("sets_detail", []):
                    ws = WorkoutSet(
                        gym_log_id=gl.id,
                        set_number=int(s.get("set_number", 1)),
                        reps=int(s.get("reps", 1)),
                        weight=float(s.get("weight", 0.0)),
                        completed=True,
                    )
                    db.session.add(ws)

                saved_exercises.append(ex["exercise"])

            draft.state = "confirmed"
            db.session.commit()
            return {
                "success": True,
                "message": f"Successfully logged workout with {len(saved_exercises)} exercise(s)!",
                "reply": f"✅ Great workout! I've saved {len(saved_exercises)} exercise(s) to your gym log.",
                "saved_exercises": saved_exercises,
                "draft": draft.to_dict()
            }
        else:
            return {"success": False, "error": "Unknown log type.", "reply": "Unknown log type.", "code": 400}

    except Exception as e:
        db.session.rollback()
        return {"success": False, "error": f"Failed to persist draft: {str(e)}", "reply": f"⚠️ Could not save draft: {str(e)}", "code": 500}


def cancel_draft(draft_id: str, user_id: int) -> Dict[str, Any]:
    """Mark draft as cancelled."""
    draft = PendingLogDraft.query.filter_by(draft_id=draft_id, user_id=user_id).first()
    if not draft:
        return {"success": False, "error": "Draft not found or unauthorized.", "code": 404}

    draft.state = "cancelled"
    db.session.commit()
    return {
        "success": True,
        "message": "Draft was cancelled.",
        "reply": "No problem! I've cancelled that draft. Let me know if you want to log anything else.",
        "draft": draft.to_dict()
    }


def edit_draft(draft_id: str, user_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update draft items or metadata before confirmation."""
    draft = PendingLogDraft.query.filter_by(draft_id=draft_id, user_id=user_id).first()
    if not draft:
        return {"success": False, "error": "Draft not found or unauthorized.", "code": 404}

    if draft.state not in ["collecting", "awaiting_confirmation"]:
        return {"success": False, "error": "Only active drafts can be edited.", "code": 400}

    data = draft.get_data()

    if "meal" in updates and draft.log_type == "food":
        data["meal"] = updates["meal"]
        for i in data.get("items", []):
            i["meal_category"] = updates["meal"]

    if "date" in updates:
        data["date"] = updates["date"]

    if "items" in updates and draft.log_type == "food":
        data["items"] = updates["items"]
        # Recalculate totals
        data["totals"] = {
            "calories": round(sum(i.get("calories", 0.0) for i in data["items"]), 1),
            "protein": round(sum(i.get("protein", 0.0) for i in data["items"]), 1),
            "fat": round(sum(i.get("fat", 0.0) for i in data["items"]), 1),
            "sugar": round(sum(i.get("sugar", 0.0) for i in data["items"]), 1),
        }

    if "exercises" in updates and draft.log_type == "workout":
        data["exercises"] = updates["exercises"]
        data["total_estimated_calories"] = round(sum(e.get("calories", 0.0) for e in data["exercises"]), 1)

    draft.set_data(data)
    draft.state = "awaiting_confirmation"
    draft.touch()
    db.session.commit()

    return {
        "success": True,
        "message": "Draft updated.",
        "draft": draft.to_dict()
    }
