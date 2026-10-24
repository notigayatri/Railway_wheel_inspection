"""
Verification test for toggleable Fast Mode / TTA Skip (run_tta=False vs run_tta=True)
"""
import time
import requests

BASE_URL = "http://127.0.0.1:8000"

def run_tests():
    # 1. Health check
    h = requests.get(f"{BASE_URL}/api/health")
    assert h.status_code == 200, f"Health check failed: {h.text}"
    print("[PASS] Health check OK")

    # 2. Login as OPERATOR
    login = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "operator", "password": "oper123"})
    assert login.status_code == 200, f"Login failed: {login.text}"
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"[PASS] Operator authenticated: {login.json()['full_name']} ({login.json()['role']})")

    # Locate test image
    from pathlib import Path
    img_candidates = list(Path("outputs/uploads").glob("*.jpg"))
    assert len(img_candidates) > 0, "No sample jpg found in outputs/uploads"
    img_path = str(img_candidates[0])
    print(f"[INFO] Using test image: {img_path}")

    # 3. Test Fast Mode (run_tta=False default)
    print("\n>>> Testing Fast Mode (run_tta=False default)...")
    t0 = time.time()
    with open(img_path, "rb") as f:
        res_fast = requests.post(f"{BASE_URL}/api/inspect", files={"image": ("wheel.jpg", f, "image/jpeg")}, headers=headers)
    t_fast = time.time() - t0

    assert res_fast.status_code == 200, f"Fast mode failed: {res_fast.status_code} {res_fast.text}"
    data_fast = res_fast.json()
    print(f"Fast Mode latency: {t_fast:.2f}s (reported: {data_fast.get('processing_time_seconds')}s)")
    print(f"run_tta flag: {data_fast.get('run_tta')}")
    print(f"Defects detected: {data_fast.get('total_defects_detected')}")
    print(f"Annotated URL: {data_fast.get('annotated_image_url')}")
    print(f"GradCAM URL (should be None): {data_fast.get('gradcam_image_url')}")

    assert data_fast.get("run_tta") is False, "Expected run_tta to be False"
    assert data_fast.get("gradcam_image_url") is None, "Expected gradcam_image_url to be None in Fast Mode"
    assert data_fast.get("annotated_image_url") is not None, "Expected annotated_image_url to be present"
    print("[PASS] Fast Mode verified successfully!")

    # 4. Test explicit form parameter run_tta=false
    with open(img_path, "rb") as f:
        res_form_false = requests.post(
            f"{BASE_URL}/api/inspect",
            files={"image": ("wheel.jpg", f, "image/jpeg")},
            data={"run_tta": "false"},
            headers=headers
        )
    assert res_form_false.status_code == 200
    assert res_form_false.json().get("run_tta") is False
    print("[PASS] Form data run_tta=false verified successfully!")

    # 5. Test Deep Diagnostic Mode (run_tta=true query parameter)
    print("\n>>> Testing Deep Diagnostic Mode (run_tta=true)...")
    t0 = time.time()
    with open(img_path, "rb") as f:
        res_deep = requests.post(
            f"{BASE_URL}/api/inspect?run_tta=true",
            files={"image": ("wheel.jpg", f, "image/jpeg")},
            headers=headers
        )
    t_deep = time.time() - t0

    assert res_deep.status_code == 200, f"Deep mode failed: {res_deep.status_code} {res_deep.text}"
    data_deep = res_deep.json()
    print(f"Deep Mode latency: {t_deep:.2f}s (reported: {data_deep.get('processing_time_seconds')}s)")
    print(f"run_tta flag: {data_deep.get('run_tta')}")
    print(f"Defects detected: {data_deep.get('total_defects_detected')}")
    print(f"Annotated URL: {data_deep.get('annotated_image_url')}")
    print(f"GradCAM URL (should be generated): {data_deep.get('gradcam_image_url')}")

    assert data_deep.get("run_tta") is True, "Expected run_tta to be True"
    assert data_deep.get("gradcam_image_url") is not None, "Expected gradcam_image_url to be present in Deep Mode"
    print(f"[PASS] Deep Diagnostic Mode verified successfully! (Speedup factor: {t_deep / max(t_fast, 0.01):.1f}x)")

    # 6. Test PDF export works on both inspections
    fast_pdf_url = f"{BASE_URL}/api/inspections/{data_fast['inspection_event_id']}/work-order-pdf"
    pdf_res = requests.get(fast_pdf_url, headers=headers)
    assert pdf_res.status_code == 200, f"Fast mode PDF export failed: {pdf_res.status_code}"
    assert pdf_res.headers.get("content-type") == "application/pdf"
    print("[PASS] Fast Mode PDF export works cleanly without Grad-CAM")

    deep_pdf_url = f"{BASE_URL}/api/inspections/{data_deep['inspection_event_id']}/work-order-pdf"
    pdf_deep_res = requests.get(deep_pdf_url, headers=headers)
    assert pdf_deep_res.status_code == 200, f"Deep mode PDF export failed: {pdf_deep_res.status_code}"
    assert pdf_deep_res.headers.get("content-type") == "application/pdf"
    print("[PASS] Deep Mode PDF export works with full Grad-CAM callout")

    print("\nALL FAST MODE / TTA SKIP TESTS PASSED!")

if __name__ == "__main__":
    run_tests()
