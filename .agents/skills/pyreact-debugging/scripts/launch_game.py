"""Launch an isolated, owner-bound MCDevTool game instance."""
import sys
import instances


def main():
    sys.argv[1:1] = ["start"]
    return instances.main()


if __name__ == "__main__":
    sys.exit(main())
