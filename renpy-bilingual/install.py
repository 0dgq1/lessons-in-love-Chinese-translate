"""Install into a user-owned game: python install.py PATH_TO_GAME_ROOT."""
import argparse
import shutil
import ssl
from pathlib import Path


def install(root):
    package = Path(__file__).resolve().parent
    game = root.resolve() / 'game'
    screen = game / 'screens.rpy'
    if not screen.is_file():
        raise SystemExit('Expected game/screens.rpy under the selected game root.')
    original = screen.read_bytes()
    source = original.decode('utf-8-sig')
    if 'lil_bilingual.runtime.enabled' not in source:
        anchor = '        text what id "what"'
        if source.count(anchor) != 1:
            raise SystemExit('Cannot locate a unique dialogue text. No game files changed.')
        fragment = (package / 'say_screen_fragment.txt').read_text(encoding='utf-8').rstrip('\n')
        newline = '\r\n' if b'\r\n' in original else '\n'
        updated = source.replace(anchor, fragment.replace('\n', newline))
        say = 'screen say(who, what):'
        if updated.count(say) != 1:
            raise SystemExit('Cannot locate a unique say screen. No game files changed.')
        updated = updated.replace(say, say + newline + '    on "hide" action Function(bilingual_stop)', 1)
        backup = game / 'bilingual_backup' / 'screens.rpy.original'
        backup.parent.mkdir(exist_ok=True)
        if not backup.exists():
            backup.write_bytes(original)
        screen.write_text(updated, encoding='utf-8', newline='')
    for relative in ('bilingual.rpy', 'python-packages/lil_bilingual.py', 'bilingual_config.example.json'):
        destination = game / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            backup = game / 'bilingual_backup' / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                shutil.copyfile(destination, backup)
        shutil.copyfile(package / 'game' / relative, destination)
    for name in ('bilingual_config.json', 'bilingual_glossary.json'):
        destination = game / name
        if not destination.exists():
            source = 'bilingual_config.example.json' if name == 'bilingual_config.json' else name
            shutil.copyfile(package / 'game' / source, destination)
    if hasattr(ssl, 'enum_certificates'):
        certificates = set()
        for store in ('ROOT', 'CA'):
            for der, encoding, trust in ssl.enum_certificates(store):
                if encoding == 'x509_asn' and (trust is True or '1.3.6.1.5.5.7.3.1' in trust):
                    certificates.add(ssl.DER_cert_to_PEM_cert(der))
        destination = game / 'bilingual_certs' / 'windows-ca.pem'
        destination.parent.mkdir(exist_ok=True)
        destination.write_text(''.join(sorted(certificates)), encoding='ascii')
    font = Path('C:/Windows/Fonts/msyh.ttc')
    if font.is_file():
        destination = game / 'bilingual_fonts' / font.name
        destination.parent.mkdir(exist_ok=True)
        if not destination.exists():
            shutil.copyfile(font, destination)
    print('Installed. Configure game/bilingual_config.json, then restart the game.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game_root', type=Path)
    install(parser.parse_args().game_root)
