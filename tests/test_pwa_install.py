import pytest

class TestPWAInstallUI:
    def test_pwa_install_elements_on_login(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        
        # Verify containers exist
        assert 'id="pwa-install-container"' in html
        assert 'id="pwaFloatingBtn"' in html
        assert 'id="pwaToast"' in html
        
        # Verify app logo and text references
        assert 'alt="VitalLog Logo"' in html
        assert 'Install VitalLog' in html
        assert 'Faster launch' in html
        
        # Verify buttons exist
        assert 'id="pwaInstallBtn"' in html
        assert 'id="pwaCancelBtn"' in html
        
        # Verify iOS Safarai fallback text is present
        assert 'id="pwaIosInstructions"' in html
        assert 'Add to Home Screen' in html
        
        # Verify Android Chrome/Samsung fallback text is present
        assert 'id="pwaAndroidInstructions"' in html
        assert 'androidChromeFallback' in html
        assert 'androidSamsungFallback' in html

    def test_pwa_install_elements_on_register(self, client):
        resp = client.get("/register")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        
        assert 'id="pwa-install-container"' in html
        assert 'id="pwaFloatingBtn"' in html
        assert 'id="pwaToast"' in html
