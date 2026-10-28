"""Giriş noktası. Argümansız çalışırsa arayüzü açar; `--cli KULLANICI [TOKEN]` ile konsolda rapor verir."""

import sys


def cli(argv):
    from ghanaliz import core
    client = core.GitHubClient(argv[1] if len(argv) > 1 else "")
    rep = core.analyze(client, argv[0], progress=lambda m, p: print(f"[{p:3d}%] {m}", file=sys.stderr))
    print(core.export_markdown(rep))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--cli":
        cli(sys.argv[2:])
    else:
        from ghanaliz.app import main
        main()
