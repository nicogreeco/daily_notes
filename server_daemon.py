"""Linux-friendly entrypoint for the generic Telegram/audio daemon."""

from termux_daemon import main


if __name__ == "__main__":
    raise SystemExit(main())

