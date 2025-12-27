import time
for i in range(5):
    status_actor.set_log_line.remote(f"Simulación línea {i}")
    time.sleep(1)
