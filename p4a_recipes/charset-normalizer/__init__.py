import os
from pythonforandroid.recipe import Recipe


class CharsetNormalizerHyphenRecipe(Recipe):
    """
    Hyphen-named recipe variant for charset-normalizer on Android.
    """
    version = "2.1.1"
    url = None
    dir_name = "charset-normalizer"
    depends = ["python3"]
    conflicts = []

    def should_build(self, arch):
        return True

    def build_arch(self, arch):
        arch_name = arch.arch if hasattr(arch, "arch") else str(arch)
        targets = []
        if hasattr(self.ctx, "get_site_packages_dir"):
            try:
                targets.append(self.ctx.get_site_packages_dir(arch))
            except Exception:
                pass
        try:
            install_dir = self.ctx.get_python_install_dir(arch_name)
            targets.append(install_dir)
            import glob
            targets.extend(glob.glob(os.path.join(install_dir, "lib", "python*", "site-packages")))
        except Exception:
            pass

        code = '''"""charset_normalizer shim for Android"""
__version__ = "2.1.1"

class CharsetMatch:
    def __init__(self, encoding="utf-8"):
        self.encoding = encoding
        self.raw = b""

    def __str__(self):
        return self.encoding


class CharsetMatches:
    def __init__(self):
        self._matches = [CharsetMatch()]

    def best(self):
        return self._matches[0]

    def first(self):
        return self._matches[0]

    def __iter__(self):
        return iter(self._matches)

    def __len__(self):
        return len(self._matches)


def from_bytes(sequences, *args, **kwargs):
    return CharsetMatches()


def from_fp(fp, *args, **kwargs):
    return CharsetMatches()


def from_path(path, *args, **kwargs):
    return CharsetMatches()


def detect(byte_str, *args, **kwargs):
    return {"encoding": "utf-8", "confidence": 1.0, "language": ""}
'''
        for sp in set(targets):
            if not sp or not os.path.isdir(sp):
                continue
            pkg_dir = os.path.join(sp, "charset_normalizer")
            os.makedirs(pkg_dir, exist_ok=True)
            with open(os.path.join(pkg_dir, "__init__.py"), "w", encoding="utf-8") as f:
                f.write(code)


recipe = CharsetNormalizerHyphenRecipe()
