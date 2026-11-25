"""
Simulate exactly what the browser does when it hits loadSimulation().
Tests the DOM querySelector logic in a Python equivalent.
"""

# Reproduce the JS logic in Python to find the bug
# The key question: does $$('#sim-type option').length return 0 on first load?

# In HTML: <select id="sim-type"></select>  — empty, no options
# JS: $$('#sim-type option') = querySelectorAll('#sim-type option') = []
# [].length = 0  → !0 = True → should enter the if block

# BUT: what if the view section itself has display:none via CSS?
# CSS: .view { display: none; }  .view.active { display: block; }
# querySelectorAll DOES work on hidden elements in browsers
# So that's not blocking it.

# Let's check: could the issue be that the view is rendered but
# loadSimulation() throws an error before innerHTML is set?

# Check: what does loadSimulation() actually do step by step?
# 1. if (!$$('#sim-type option').length)  → true when empty
# 2. types = [...]
# 3. $('#sim-type').innerHTML = types.map(...).join('')
#    → This needs $('#sim-type') to return the element
#    → If view-simulation section is hidden with display:none,
#       querySelector STILL returns the element
#    → So this should work

# WAIT — let me re-read the CSS carefully
print("Checking CSS .view class:")
css_content = open(r"C:\Users\impana\AI_Project\AI_Agent\AI_Agent\frontend\css\styles.css").read()
# find .view rule
import re
matches = re.findall(r'\.view\s*\{[^}]+\}', css_content)
for m in matches:
    print(" ", m.strip())

print()
print("Checking .hidden rule:")
matches = re.findall(r'\.hidden\s*\{[^}]+\}', css_content)
for m in matches:
    print(" ", m.strip())

print()
# The real question: is there anything that could cause the innerHTML assignment to fail?
# Let's check if '#sim-type' exists in the HTML
html = open(r"C:\Users\impana\AI_Project\AI_Agent\AI_Agent\frontend\index.html").read()
print("sim-type in HTML:", 'id="sim-type"' in html)
print("sim-severity in HTML:", 'id="sim-severity"' in html)
print("view-simulation in HTML:", 'id="view-simulation"' in html)

# Check: does view-simulation appear INSIDE app-shell?
idx_shell_start = html.find('id="app-shell"')
idx_sim = html.find('id="view-simulation"')
idx_shell_end = html.find('</div>\n\n<script')  # end of app-shell
print(f"\napp-shell starts at char: {idx_shell_start}")
print(f"view-simulation at char: {idx_sim}")
print(f"shell ends around char: {idx_shell_end}")
print("view-simulation is INSIDE app-shell:", idx_shell_start < idx_sim < idx_shell_end)

# Check the app-shell's initial class
import re
shell_match = re.search(r'id="app-shell"[^>]*class="([^"]*)"', html)
print(f"\napp-shell initial class: '{shell_match.group(1) if shell_match else 'NOT FOUND'}'")

# CRITICAL: app-shell starts with class="app hidden"
# The loadSimulation() function is called from loadView() which is called from navigate()
# navigate() is called from showApp() — AFTER app-shell.classList.remove('hidden')
# So by the time loadSimulation runs, app-shell is visible
# BUT: the .hidden class uses display:none !important
# When app-shell has 'hidden', ALL children including sim-type select are hidden
# querySelectorAll still works on hidden elements though

# Let me check the ACTUAL problem: look at what happens with the CSS rule
print("\n--- Checking if .hidden affects querySelector ---")
print("Note: querySelector/querySelectorAll DO work on elements with display:none")
print("So CSS hiding is NOT the cause")

print("\n--- Checking for JavaScript errors that could silently swallow ---")
print("loadView() wraps everything in try/catch -> toast()")
print("So if loadSimulation() throws, user sees a toast, not a console error")
print("But if the toast fires too fast and disappears, user might miss it")

print("\n--- Checking: does $$() work correctly? ---")
js_content = open(r"C:\Users\impana\AI_Project\AI_Agent\AI_Agent\frontend\js\app.js").read()
# find $$ definition
match = re.search(r'const \$\$\s*=.+', js_content)
print(f"$$ definition: {match.group(0) if match else 'NOT FOUND'}")

match2 = re.search(r'const \$\s*=.+', js_content)
print(f"$ definition: {match2.group(0) if match2 else 'NOT FOUND'}")

# Check loadSimulation function exactly
sim_match = re.search(r'async function loadSimulation\(\)[^{]*\{(.+?)\n\}', js_content, re.DOTALL)
if sim_match:
    print(f"\nloadSimulation body:\n{sim_match.group(0)}")
