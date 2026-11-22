#!/usr/bin/env python3
"""
Cross-platform (Windows / Linux / macOS) Sahibinden Cookie Exporter & Coolify Uploader.

Exports your own Sahibinden browser session cookies WITHOUT any 3rd-party browser extension:
  1) --browser : Opens a visible Playwright browser window so you can sign in yourself,
                 then saves all sahibinden.com cookies (including HttpOnly) as JSON.
  2) --paste   : Zero-dependency mode; paste the 'Cookie:' request header copied from
                 F12 DevTools -> Network and convert it into clean JSON.

Then uploads directly to Coolify / Docker via:
  - One-line Coolify Web Terminal command (base64, copy-paste safe, zero SSH needed)
  - Direct SSH streaming into the running Coolify container (no temp files on server)
  - Local Docker (`docker cp`)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from typing import Any

PERSISTENT_COOKIE_TTL_SECONDS = 30 * 86400  # 30 days fallback for session-only cookies
DEFAULT_OUTPUT_PATH = Path("sahibinden_cookies.json")
DEFAULT_REMOTE_PATH = "/app/data/sahibinden_cookies.json"


def _is_sahibinden_domain(domain: str) -> bool:
    bare = (domain or "").strip().lower().lstrip(".")
    return bare == "sahibinden.com" or bare.endswith(".sahibinden.com")


def parse_cookie_header(header_value: str, ttl_seconds: int = PERSISTENT_COOKIE_TTL_SECONDS) -> list[dict[str, Any]]:
    """Parse a raw F12 DevTools 'Cookie:' header string into Playwright-compatible cookie dicts."""
    text = (header_value or "").strip()
    if text.lower().startswith("cookie:"):
        text = text[len("cookie:"):].strip()
    if not text:
        return []

    by_name: dict[str, str] = {}
    for part in text.split(";"):
        chunk = part.strip()
        if "=" not in chunk:
            continue
        name, value = chunk.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name:
            by_name[name] = value

    exp = float(time.time() + ttl_seconds)
    return [
        {
            "name": name,
            "value": value,
            "domain": ".sahibinden.com",
            "path": "/",
            "secure": True,
            "expires": exp,
        }
        for name, value in by_name.items()
    ]


def normalize_sahibinden_cookies(
    raw_cookies: list[dict[str, Any]],
    ttl_seconds: int = PERSISTENT_COOKIE_TTL_SECONDS,
) -> list[dict[str, Any]]:
    """Filter strictly to sahibinden.com domains and promote session-only cookies to persistent TTL."""
    same_site_map = {
        "none": "None",
        "no_restriction": "None",
        "lax": "Lax",
        "strict": "Strict",
    }
    fallback_exp = float(time.time() + ttl_seconds)
    result: list[dict[str, Any]] = []
    for entry in raw_cookies:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        value = entry.get("value")
        domain = str(entry.get("domain") or "").strip().lower()
        if not name or value is None or not _is_sahibinden_domain(domain):
            continue

        cookie: dict[str, Any] = {
            "name": name,
            "value": str(value),
            "domain": domain,
            "path": str(entry.get("path") or "/"),
        }
        if "httpOnly" in entry:
            cookie["httpOnly"] = bool(entry["httpOnly"])
        if "secure" in entry:
            cookie["secure"] = bool(entry["secure"])

        raw_ss = entry.get("sameSite")
        if isinstance(raw_ss, str):
            mapped = same_site_map.get(raw_ss.strip().lower())
            if mapped:
                cookie["sameSite"] = mapped

        raw_exp = entry.get("expires", entry.get("expirationDate"))
        if isinstance(raw_exp, (int, float)) and raw_exp > 0:
            cookie["expires"] = float(raw_exp)
        else:
            cookie["expires"] = fallback_exp

        result.append(cookie)
    return result


def write_cookies_json(cookies: list[dict[str, Any]], output_path: Path) -> Path:
    """Write normalized cookies in Playwright storage_state JSON format with restrictive permissions."""
    payload = {"cookies": cookies}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(output_path, 0o600)
    except OSError:
        pass
    return output_path


def build_coolify_terminal_command(
    cookies_path: Path,
    remote_path: str = DEFAULT_REMOTE_PATH,
) -> str:
    """Build a single-line base64 command safe for pasting into Coolify's Web Terminal."""
    raw_bytes = cookies_path.read_bytes()
    b64 = base64.b64encode(raw_bytes).decode("ascii")
    return f"echo '{b64}' | base64 -d > {remote_path} && chmod 600 {remote_path} && ls -lh {remote_path}"


def copy_to_clipboard(text: str) -> bool:
    """Best-effort cross-platform clipboard copy (Windows clip, macOS pbcopy, Linux wl-copy/xclip/xsel)."""
    system = platform.system().lower()
    candidates: list[list[str]] = []
    if system == "windows":
        candidates.append(["clip"])
    elif system == "darwin":
        candidates.append(["pbcopy"])
    else:
        candidates.extend([["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]])

    for cmd in candidates:
        if shutil.which(cmd[0]) is None:
            continue
        try:
            subprocess.run(cmd, input=text.encode("utf-8"), check=True)
            return True
        except Exception:
            continue
    return False


def export_via_browser(browser_channel: str | None = None) -> list[dict[str, Any]]:
    """Open an official visible Playwright browser so the user signs in and exports cookies."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright yüklü değil. '--paste' modunu kullanabilir veya "
            "'pip install playwright && playwright install chromium' çalıştırabilirsiniz."
        ) from exc

    print("\n[1/2] Tarayıcı açılıyor... Lütfen açılan pencerede kendi Sahibinden hesabınızla giriş yapın.")
    with sync_playwright() as p:
        launch_kwargs: dict[str, Any] = {"headless": False}
        if browser_channel:
            launch_kwargs["channel"] = browser_channel
        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context(locale="tr-TR", timezone_id="Europe/Istanbul")
        page = context.new_page()
        page.goto("https://www.sahibinden.com/", timeout=30000)

        input("\n>>> Giriş işlemini tamamladıktan sonra bu terminale dönüp ENTER tuşuna basın...")
        raw_cookies = context.cookies(["https://www.sahibinden.com", "https://secure.sahibinden.com"])
        browser.close()

    return normalize_sahibinden_cookies(raw_cookies)


def export_via_paste(header_value: str | None = None) -> list[dict[str, Any]]:
    """Convert a pasted F12 DevTools 'Cookie:' request header into normalized JSON cookies."""
    if not header_value:
        print(
            "\nTarayıcınızda sahibinden.com'a giriş yaptıktan sonra:\n"
            "  F12 -> Network (Ağ) -> F5 -> ilk 'www.sahibinden.com' isteği ->\n"
            "  Headers -> Request Headers -> 'Cookie:' değerini kopyalayın.\n"
        )
        header_value = input("Kopyaladığınız Cookie değerini buraya yapıştırıp ENTER'a basın:\n> ").strip()
    return parse_cookie_header(header_value)


def upload_via_ssh(
    cookies_path: Path,
    ssh_target: str,
    container_name: str | None = None,
    remote_path: str = DEFAULT_REMOTE_PATH,
) -> None:
    """Stream cookies JSON directly over SSH into the running Coolify/Docker container (no server temp files)."""
    if shutil.which("ssh") is None:
        raise RuntimeError("'ssh' komutu bulunamadı. Coolify Terminal tek-satır komutunu kullanabilirsiniz.")

    if not container_name:
        detect_cmd = (
            "docker ps --format '{{.Names}}' | "
            "grep -E 'sahibinden(-discord)?-bot' | head -n 1"
        )
        res = subprocess.run(
            ["ssh", ssh_target, detect_cmd],
            capture_output=True,
            text=True,
            check=True,
        )
        container_name = res.stdout.strip()
        if not container_name:
            raise RuntimeError(
                "Sunucuda çalışan sahibinden bot konteyneri otomatik bulunamadı. "
                "'--container <konteyner_adi>' parametresi ile belirtin."
            )
        print(f"Bulunan konteyner: {container_name}")

    remote_cmd = f"docker exec -i {container_name} sh -c 'cat > {remote_path} && chmod 600 {remote_path}'"
    subprocess.run(
        ["ssh", ssh_target, remote_cmd],
        input=cookies_path.read_bytes(),
        check=True,
    )
    print(f"✅ Çerezler SSH ile '{ssh_target}' -> '{container_name}:{remote_path}' yoluna yüklendi!")


def upload_via_local_docker(
    cookies_path: Path,
    container_name: str | None = None,
    remote_path: str = DEFAULT_REMOTE_PATH,
) -> None:
    """Copy cookies JSON directly into a local Docker/WSL container."""
    if shutil.which("docker") is None:
        raise RuntimeError("'docker' komutu bulunamadı.")

    if not container_name:
        res = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in res.stdout.splitlines():
            name = line.strip()
            if "sahibinden-discord-bot" in name or "sahibinden-bot" in name:
                container_name = name
                break
        if not container_name:
            raise RuntimeError(
                "Yerel Docker üzerinde çalışan sahibinden bot konteyneri bulunamadı. "
                "'--container <konteyner_adi>' ile belirtin."
            )
        print(f"Bulunan yerel konteyner: {container_name}")

    subprocess.run(
        ["docker", "cp", str(cookies_path), f"{container_name}:{remote_path}"],
        check=True,
    )
    print(f"✅ Çerezler yerel Docker konteynerine ({container_name}:{remote_path}) kopyalandı!")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sahibinden oturum çerezlerini eklentisiz JSON olarak dışa aktarır ve Coolify/Docker'a yükler."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--browser",
        action="store_true",
        help="Resmi Playwright tarayıcısı açarak giriş yapıp çerezleri kaydet (varsayılan).",
    )
    mode.add_argument(
        "--paste",
        action="store_true",
        help="Playwright olmadan F12 DevTools 'Cookie:' başlığını yapıştırarak JSON üret.",
    )
    parser.add_argument(
        "--cookie-header",
        default=None,
        help="--paste modunda doğrudan komut satırından Cookie başlığı geçmek için.",
    )
    parser.add_argument(
        "--channel",
        default=None,
        help="İsteğe bağlı tarayıcı kanalı (--browser için: 'chrome' veya 'msedge').",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Çıktı JSON dosya yolu (varsayılan: {DEFAULT_OUTPUT_PATH}).",
    )
    parser.add_argument(
        "--ssh",
        default=None,
        help="Coolify/VPS sunucusuna SSH ile doğrudan yükle (örn: root@1.2.3.4).",
    )
    parser.add_argument(
        "--local-docker",
        action="store_true",
        help="Yerel Docker / WSL konteynerine 'docker cp' ile yükle.",
    )
    parser.add_argument(
        "--container",
        default=None,
        help="Hedef Docker konteyner adı (boş bırakılırsa otomatik bulunur).",
    )
    parser.add_argument(
        "--remote-path",
        default=DEFAULT_REMOTE_PATH,
        help=f"Konteyner içi hedef dosya yolu (varsayılan: {DEFAULT_REMOTE_PATH}).",
    )
    parser.add_argument(
        "--print-coolify-cmd",
        action="store_true",
        help="Coolify Web Terminal için tek-satırlık yükleme komutunu yazdır.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # 1. Export cookies
    if args.paste or args.cookie_header:
        cookies = export_via_paste(args.cookie_header)
    elif args.browser:
        cookies = export_via_browser(args.channel)
    else:
        # Interactive auto-select: prefer browser if Playwright is available, else paste
        has_playwright = False
        try:
            import playwright  # noqa: F401
            has_playwright = True
        except ImportError:
            has_playwright = False

        if has_playwright:
            print("Çerez alma yöntemi seçin:")
            print("  [1] Tarayıcı aç ve giriş yap (Playwright - Önerilen, tüm HttpOnly çerezler)")
            print("  [2] F12 DevTools 'Cookie:' satırını yapıştır (Tarayıcı açmadan)")
            choice = input("Seçiminiz [1/2] (varsayılan 1): ").strip() or "1"
            cookies = export_via_paste() if choice == "2" else export_via_browser(args.channel)
        else:
            print("Playwright kurulu değil; eklentisiz F12 'Cookie:' yapıştırma modu başlatılıyor...")
            cookies = export_via_paste()

    if not cookies:
        print("❌ Geçerli sahibinden.com çerezi bulunamadı. İşlem iptal edildi.", file=sys.stderr)
        return 1

    out_path = write_cookies_json(cookies, args.output)
    print(f"\n✅ {len(cookies)} adet sahibinden.com çerezi '{out_path}' dosyasına kaydedildi.")

    # 2. Upload to Coolify / Docker
    if args.ssh:
        upload_via_ssh(out_path, args.ssh, args.container, args.remote_path)
        return 0
    if args.local_docker:
        upload_via_local_docker(out_path, args.container, args.remote_path)
        return 0
    if args.print_coolify_cmd:
        cmd = build_coolify_terminal_command(out_path, args.remote_path)
        copied = copy_to_clipboard(cmd)
        print("\n=== Coolify Terminal Tek-Satır Yükleme Komutu ===")
        print(cmd)
        if copied:
            print("\n📋 Komut panonuza kopyalandı! Coolify -> Terminal (sahibinden-bot) ekranına yapıştırıp Enter'a basın.")
        return 0

    print("\n[2/2] Çerezleri Coolify / Docker'a nasıl yüklemek istersiniz?")
    print("  [1] Coolify Web Terminal tek-satır komutu üret (SSH gerekmez - Önerilen)")
    print("  [2] SSH ile uzak Coolify/VPS sunucusuna doğrudan yükle")
    print("  [3] Yerel Docker / WSL konteynerine kopyala")
    print("  [4] Şimdilik sadece JSON dosyasını sakla (yükleme yapma)")
    upload_choice = input("Seçiminiz [1/2/3/4] (varsayılan 1): ").strip() or "1"

    if upload_choice == "1":
        cmd = build_coolify_terminal_command(out_path, args.remote_path)
        copied = copy_to_clipboard(cmd)
        print("\n=== Coolify Terminal Tek-Satır Yükleme Komutu ===")
        print(cmd)
        if copied:
            print("\n📋 Komut otomatik olarak panonuza kopyalandı!")
        print(
            "\nCoolify -> Uygulamanız -> Terminal (sahibinden-bot) ekranına yapıştırıp Enter'a basın.\n"
            "Konteyneri yeniden başlatmanız gerekmez; bot ~5 saniye içinde otomatik yükleyip taramaya devam eder."
        )
    elif upload_choice == "2":
        ssh_target = input("SSH adresi (örn: root@123.45.67.89): ").strip()
        container = input("Konteyner adı (otomatik bulmak için boş bırakın): ").strip() or None
        if ssh_target:
            upload_via_ssh(out_path, ssh_target, container, args.remote_path)
    elif upload_choice == "3":
        container = input("Konteyner adı (otomatik bulmak için boş bırakın): ").strip() or None
        upload_via_local_docker(out_path, container, args.remote_path)
    else:
        print(f"Tamam! Dosya hazır: {out_path.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
