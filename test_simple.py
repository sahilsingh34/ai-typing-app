import sys
import os

print("Simple script running")
with open("test_simple_out.txt", "w") as f:
    f.write("Workspace path: " + os.getcwd() + "\n")
    f.write("Python executable: " + sys.executable + "\n")
    try:
        import win32com.client
        f.write("win32com: OK\n")
    except Exception as e:
        f.write("win32com: ERR: " + str(e) + "\n")
