"""Run standalone chat: python -m ada_piano.agent."""
import tkinter as tk

from .gui import CoachPanel


def main():
    from .settings import load_api_key
    load_api_key()
    root = tk.Tk()
    root.title("ADA Coach — standalone chat")
    root.geometry("1000x650")
    root.minsize(800, 560)
    panel = CoachPanel(root)
    panel.pack(fill="both", expand=True)

    def close():
        panel.close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    try:
        root.mainloop()
    finally:
        if not panel._closed:
            close()


if __name__ == "__main__":
    main()
