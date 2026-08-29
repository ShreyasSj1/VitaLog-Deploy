"""Daily Workout Challenges (WOD) catalog and helper functions."""
from datetime import datetime, date
from models import GymLog

DAILY_CHALLENGES = [
    {
        "id": 1,
        "title": "Centurion Push",
        "icon": "🔥",
        "muscle": "Chest",
        "tagline": "Build chest and triceps endurance with 100 disciplined push-ups.",
        "target": "100 Total Push-ups",
        "difficulty": "Intermediate",
        "calories": 110.0,
        "duration": 12.0,
        "instructions": [
            "Break it down: 5 sets of 20 or 10 sets of 10 reps",
            "Maintain a solid plank position without sagging hips",
            "Rest 45–60s between each set"
        ]
    },
    {
        "id": 2,
        "title": "Thunder Quads",
        "icon": "⚡",
        "muscle": "Legs",
        "tagline": "Ignite your legs with explosive bodyweight squats and walking lunges.",
        "target": "60 Air Squats + 40 Walking Lunges",
        "difficulty": "Intermediate",
        "calories": 135.0,
        "duration": 14.0,
        "instructions": [
            "Complete 3 rounds: 20 Squats + 14 Lunges (7/leg)",
            "Descend to parallel with chest proud",
            "Rest 60s between rounds"
        ]
    },
    {
        "id": 3,
        "title": "Iron Core Fortress",
        "icon": "🥋",
        "muscle": "Core",
        "tagline": "Lock in rock-solid abdominal strength and endurance.",
        "target": "3 × 60s Planks + 50 Bicycle Crunches",
        "difficulty": "All Levels",
        "calories": 95.0,
        "duration": 10.0,
        "instructions": [
            "Hold a forearm plank for 60 seconds (3 total sets)",
            "Finish with 50 smooth, controlled bicycle crunches (25/side)",
            "Keep core braced and breathe steadily"
        ]
    },
    {
        "id": 4,
        "title": "HIIT Oxygen Burner",
        "icon": "🚀",
        "muscle": "Cardio",
        "tagline": "High-intensity cardio blast to spike metabolism and burn calories fast.",
        "target": "5 Rounds: 30s High Knees + 15 Burpees",
        "difficulty": "Hard",
        "calories": 160.0,
        "duration": 15.0,
        "instructions": [
            "Perform 30s max effort high knees immediately into 15 burpees",
            "Rest 45s between rounds",
            "Aim for steady pacing and explosive jumps"
        ]
    },
    {
        "id": 5,
        "title": "Arm Annihilator",
        "icon": "💥",
        "muscle": "Arms",
        "tagline": "Intense bodyweight arm sculpting with dips and diamond pushups.",
        "target": "50 Chair/Bench Dips + 40 Diamond Push-ups",
        "difficulty": "Intermediate",
        "calories": 105.0,
        "duration": 11.0,
        "instructions": [
            "Alternate between 10 Bench Dips and 8 Diamond Push-ups (5 rounds)",
            "Focus on maximum triceps contraction at the top",
            "Rest 45s between rounds"
        ]
    },
    {
        "id": 6,
        "title": "Glute & Hamstring Inferno",
        "icon": "🏹",
        "muscle": "Legs",
        "tagline": "Target your posterior chain with glute bridges and Bulgarian split squats.",
        "target": "60 Glute Bridges + 30 Split Squats / leg",
        "difficulty": "All Levels",
        "calories": 120.0,
        "duration": 13.0,
        "instructions": [
            "Squeeze glutes at the top of each bridge for 2 seconds",
            "Perform 3 sets of 10 Bulgarian Split Squats per leg",
            "Keep weight in the front heel"
        ]
    },
    {
        "id": 7,
        "title": "Mountain Storm",
        "icon": "🏔️",
        "muscle": "Core",
        "tagline": "Cardio-core combination for dynamic stamina and shred.",
        "target": "100 Mountain Climbers + 50 Russian Twists",
        "difficulty": "Intermediate",
        "calories": 115.0,
        "duration": 10.0,
        "instructions": [
            "Break into 4 rounds: 25 Mountain Climbers + 12 Russian Twists",
            "Drive knees hard toward elbows",
            "Maintain controlled rotation on twists"
        ]
    },
    {
        "id": 8,
        "title": "Spartan Pull & Row",
        "icon": "🦍",
        "muscle": "Back",
        "tagline": "Strengthen lats, rhomboids, and rear delts.",
        "target": "40 Pull-ups / Inverted Rows + 50 Superman Extensions",
        "difficulty": "Intermediate",
        "calories": 125.0,
        "duration": 12.0,
        "instructions": [
            "Perform 4-5 sets of Pull-ups or bodyweight Australian Inverted Rows",
            "Pair with 50 floor Supermans (5 sets of 10)",
            "Focus on pulling through your elbows"
        ]
    },
    {
        "id": 9,
        "title": "Tabata Torch 4-Minute Sprint",
        "icon": "⏱️",
        "muscle": "Cardio",
        "tagline": "Pure 4-minute maximum aerobic capacity booster (20s on / 10s off).",
        "target": "8 Rounds (20s Max Sprint/Jump Rope + 10s Rest)",
        "difficulty": "Hard",
        "calories": 140.0,
        "duration": 8.0,
        "instructions": [
            "20 seconds 100% all-out effort (Jump Rope, Shadowbox, or Fast Jumping Jacks)",
            "10 seconds complete rest",
            "Repeat for 8 continuous cycles (4 minutes total)"
        ]
    },
    {
        "id": 10,
        "title": "Shoulder Boulder Shield",
        "icon": "🧗‍♂️",
        "muscle": "Shoulders",
        "tagline": "Build deltoid stamina and overhead pressing power.",
        "target": "50 Pike Push-ups + 60s Wall Handstand/Plank Hold",
        "difficulty": "Intermediate",
        "calories": 100.0,
        "duration": 10.0,
        "instructions": [
            "Perform 5 sets of 10 Pike Push-ups to target the shoulders",
            "Finish with 2 sets of 30s Wall-assisted handstand holds or high pike holds",
            "Keep shoulders engaged throughout"
        ]
    },
    {
        "id": 11,
        "title": "The 300 Rep Bodyweight Gauntlet",
        "icon": "👑",
        "muscle": "Full Body",
        "tagline": "The ultimate full-body test: 100 Squats + 100 Push-ups + 100 Crunches.",
        "target": "100 Squats + 100 Push-ups + 100 Crunches",
        "difficulty": "Hard",
        "calories": 180.0,
        "duration": 18.0,
        "instructions": [
            "Do 10 rounds: 10 Squats, 10 Push-ups, 10 Crunches",
            "Time yourself and try to beat your personal best",
            "Maintain crisp form on every single rep"
        ]
    },
    {
        "id": 12,
        "title": "Calf & Ankle Spring",
        "icon": "⚡",
        "muscle": "Legs",
        "tagline": "Explosive lower leg and athletic spring conditioning.",
        "target": "150 Calf Raises + 100 Pogo Hops",
        "difficulty": "All Levels",
        "calories": 90.0,
        "duration": 9.0,
        "instructions": [
            "Complete 3 sets of 50 standing calf raises on a step edge",
            "Follow each set with 30 rapid, light pogo hops on your toes",
            "Feel the stretch at the bottom and hard flex at the top"
        ]
    },
    {
        "id": 13,
        "title": "V-Up & Hollow Body Matrix",
        "icon": "🌀",
        "muscle": "Core",
        "tagline": "Gymnastic core conditioning for elite midline stability.",
        "target": "40 V-Ups + 4 × 30s Hollow Body Holds",
        "difficulty": "Intermediate",
        "calories": 95.0,
        "duration": 10.0,
        "instructions": [
            "Alternate: 10 V-ups followed immediately by a 30s hollow hold",
            "Repeat for 4 intense rounds",
            "Press lower back firmly into the floor"
        ]
    },
    {
        "id": 14,
        "title": "Warrior Shadowbox Round",
        "icon": "🥊",
        "muscle": "Cardio",
        "tagline": "Rhythm, rotation, and cardio burn inspired by boxing training.",
        "target": "3 Rounds × 3 Minutes Active Shadowboxing",
        "difficulty": "All Levels",
        "calories": 150.0,
        "duration": 12.0,
        "instructions": [
            "Round 1: Jabs, crosses, and light bouncing footwork",
            "Round 2: Hooks, uppercuts, and head movement slips",
            "Round 3: High-tempo non-stop combinations"
        ]
    }
]


def get_daily_challenge(date_str: str) -> dict:
    """Deterministically returns the daily workout challenge for any given ISO date string."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        dt = date.today()

    # Days since epoch determines the rotation through the catalog
    days_since_epoch = (dt - date(2026, 1, 1)).days
    index = abs(days_since_epoch) % len(DAILY_CHALLENGES)
    challenge = dict(DAILY_CHALLENGES[index])
    challenge["date"] = dt.isoformat()
    return challenge


def is_challenge_completed(user_id: int, date_str: str, challenge_title: str) -> bool:
    """Checks if the given challenge has already been logged by the user for the date."""
    exercise_name = f"Daily Challenge: {challenge_title}"
    entry = GymLog.query.filter_by(
        user_id=user_id,
        date=date_str,
        exercise=exercise_name
    ).first()
    return entry is not None
