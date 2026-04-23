import re

text = """
 ○김민수 의원 존경하는 충남 도민 여
"""

for m in re.finditer(r'(?m)^[○◯][^\n]+', text):
    print("NO LEADING SPACE MATCH:", m.group(0))

for m in re.finditer(r'(?m)^[ \t]*[○◯][^\n]+', text):
    print("LEADING SPACE MATCH:", m.group(0))
