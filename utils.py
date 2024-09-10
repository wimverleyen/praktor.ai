from settings import create_log

log = create_log()


def read_markdown(filename):
    result = ''
    try:
        with open(filename, 'r') as f:
            result = f.read()
    except Exception as e:
        print(f"ERROR: {e}")
        log.error(f"ERROR: {e}")
    return result

def save_markdown(filename, text):
    try:
        with open(filename, 'w') as f:
            f.write(text)
    except Exception as e:
        print(f"ERROR: {e}")
        log.error(f"ERROR: {e}")