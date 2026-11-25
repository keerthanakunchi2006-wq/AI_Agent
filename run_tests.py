import subprocess, os, tempfile
py = r"C:\Users\impana\AppData\Local\Python\pythoncore-3.14-64\python.exe"
backend = r"C:\Users\impana\AI_Project\AI_Agent\AI_Agent\backend"
test_db = os.path.join(tempfile.gettempdir(), "sc_test.db")
if os.path.exists(test_db): os.remove(test_db)
result = subprocess.run([py, "-m", "pytest", "tests/", "-v", "--tb=short"],
    cwd=backend, capture_output=True, text=True, timeout=300)
print(result.stdout)
if result.returncode != 0: print("STDERR:", result.stderr[:800])
print("RC:", result.returncode)
