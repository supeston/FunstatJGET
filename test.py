import os
import sys
import time
import subprocess

bot_script = "main.py"

def get_mtime():
    try:
        return os.path.getmtime(bot_script)
    except OSError:
        return 0

def main():
    print(f"[*] Starting hot-reloader for {bot_script}...")
    last_mtime = get_mtime()
    process = None
    
    try:
        # Start bot in a subprocess with unbuffered output
        process = subprocess.Popen([sys.executable, "-u", bot_script])
        print(f"[*] Bot started (PID: {process.pid})")
        
        while True:
            time.sleep(1)
            current_mtime = get_mtime()
            
            # Watch for modification time changes
            if current_mtime != last_mtime:
                print(f"\\n[*] File {bot_script} changed! Reloading...")
                last_mtime = current_mtime
                
                # Terminate running instance
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                
                # Restart bot
                process = subprocess.Popen([sys.executable, "-u", bot_script])
                print(f"[*] Bot restarted (PID: {process.pid})")
                
            # If the bot process exits, restart it
            if process.poll() is not None:
                exit_code = process.poll()
                print(f"[!] Bot process exited with code {exit_code}. Restarting in 3 seconds...")
                time.sleep(3)
                process = subprocess.Popen([sys.executable, "-u", bot_script])
                print(f"[*] Bot restarted (PID: {process.pid})")
                
    except KeyboardInterrupt:
        print("\\n[*] Shutting down hot-reloader...")
        if process:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        print("[*] Done!")

if __name__ == "__main__":
    main()
