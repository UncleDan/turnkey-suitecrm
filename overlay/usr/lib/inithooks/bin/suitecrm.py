#!/usr/bin/python3
import sys
import getopt
import os
import subprocess
from hashlib import md5
from libinithooks.dialog_wrapper import Dialog
from mysqlconf import MySQL

DEFAULT_DOMAIN = "www.example.com"
WEBROOT = "/var/www/suitecrm"
CONF_FILE = "/etc/apache2/sites-available/suitecrm.conf"

def is_ssl_enabled():
    if os.path.exists(CONF_FILE):
        with open(CONF_FILE, 'r') as f:
            return "SSLEngine on" in f.read()
    return False

def main():
    opts, _ = getopt.gnu_getopt(sys.argv[1:], "h", ['help', 'pass=', 'domain='])
    password = domain = ""

    for opt, val in opts:
        if opt in ('-h', '--help'): sys.exit()
        elif opt == '--pass': password = val
        elif opt == '--domain': domain = val

    if not password:
        password = Dialog('TurnKey').get_password("SuiteCRM Password", "Enter admin password.")
    if not domain:
        domain = Dialog('TurnKey').get_input("SuiteCRM Domain", "Enter domain.", DEFAULT_DOMAIN)

    domain_clean = domain.replace('http://', '').replace('https://', '').strip('/')
    protocol = "https" if is_ssl_enabled() else "http"
    site_url = f"{protocol}://{domain_clean}"

    # 1. Update Legacy Config (config.php)
    conf_path = f'{WEBROOT}/public/legacy/config.php'
    if os.path.exists(conf_path):
        with open(conf_path, 'r') as f:
            lines = f.readlines()
        with open(conf_path, 'w') as f:
            for line in lines:
                if "'site_url'" in line:
                    fob.write(f"  'site_url' => '{site_url}',\n")
                else:
                    fob.write(line)

    # 2. Update Database Password (BCRYPT of MD5)
    password_md5 = md5(password.encode()).hexdigest()
    hash_pass = subprocess.run([
        'php', '-r', 'echo password_hash($argv[1], PASSWORD_BCRYPT);', password_md5
    ], capture_output=True, text=True).stdout.strip()

    m = MySQL()
    m.execute('UPDATE suitecrm.users SET user_hash=%s WHERE user_name="admin";', (hash_pass,))

    # 3. CRITICAL: Clear Symfony Cache for Domain Update
    # SuiteCRM 8 maps the site_url into the compiled container.
    # Without this, you get 500 errors or redirects to 'localhost'.
    subprocess.run(['sudo', '-u', 'www-data', f'{WEBROOT}/bin/console', 'cache:clear'], cwd=WEBROOT)

    print(f"Configured for {site_url}")

if __name__ == "__main__":
    main()