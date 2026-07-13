import pytest
import xml.etree.ElementTree as ET

class TestTechnicalSEO:
    def test_robots_txt(self, client):
        resp = client.get("/robots.txt")
        assert resp.status_code == 200
        assert resp.mimetype == "text/plain"
        
        content = resp.data.decode("utf-8")
        assert "User-agent: *" in content
        assert "Allow: /login" in content
        assert "Allow: /register" in content
        assert "Allow: /forgot-password" in content
        assert "Disallow: /food" in content
        assert "Disallow: /sleep" in content
        assert "Disallow: /wellbeing" in content
        assert "Disallow: /gym" in content
        assert "Disallow: /report" in content
        assert "Disallow: /profile" in content
        assert "Disallow: /admin" in content
        assert "Sitemap:" in content

    def test_sitemap_xml(self, client):
        resp = client.get("/sitemap.xml")
        assert resp.status_code == 200
        assert resp.mimetype == "application/xml"
        
        xml_content = resp.data.decode("utf-8")
        # Parse XML to verify valid structure
        root = ET.fromstring(xml_content)
        assert "urlset" in root.tag
        
        # Extract loc elements
        urls = [loc.text for loc in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
        assert len(urls) == 3
        assert "http://localhost/login" in urls
        assert "http://localhost/register" in urls
        assert "http://localhost/forgot-password" in urls

    def test_favicon_ico(self, client):
        resp = client.get("/favicon.ico")
        assert resp.status_code == 200
        assert resp.mimetype == "image/png"

    def test_login_page_seo_tags(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        
        # Verify title & description
        assert "<title>Login | VitalLog Fitness Tracker</title>" in html
        assert 'name="description" content="Log in to track your calories, protein, sleep, workouts, and wellbeing with VitalLog&#39;s AI fitness coach."' in html
        
        # Verify Canonical link
        assert '<link rel="canonical" href="http://localhost/login">' in html
        
        # Verify Open Graph
        assert 'property="og:title" content="Login | VitalLog Fitness Tracker"' in html
        assert 'property="og:type" content="website"' in html
        
        # Verify Twitter
        assert 'name="twitter:card" content="summary_large_image"' in html
        assert 'name="twitter:title" content="Login | VitalLog Fitness Tracker"' in html

        # Verify Form accessibility elements
        assert 'for="email"' in html
        assert 'id="email"' in html
        assert 'for="password"' in html
        assert 'id="password"' in html

    def test_register_page_seo_tags(self, client):
        resp = client.get("/register")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        
        assert "<title>Register | VitalLog Fitness Tracker</title>" in html
        assert 'name="description" content="Create your account to start tracking calories, workouts, sleep, and wellbeing with your personal AI Fitness Coach."' in html
        assert '<link rel="canonical" href="http://localhost/register">' in html
        
        # Verify Form accessibility elements
        assert 'for="name"' in html
        assert 'id="name"' in html
        assert 'for="confirm_password"' in html
        assert 'id="confirm_password"' in html
