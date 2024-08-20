import json
import os
from fake_useragent import UserAgent

# ANSI escape sequences for colors
GREEN_TEXT = "\033[92m"
RED_TEXT = "\033[91m"
RESET_TEXT = "\033[0m"

# Print authorship information and warnings in colors
print(f"{GREEN_TEXT}Program created by @Hekman316, modifications by @KeyGen_KeyGen{RESET_TEXT}")
print(f"{RED_TEXT}NOT FOR SALE!{RESET_TEXT}")
print(f"{GREEN_TEXT}GitHub link to the bot: https://github.com/shamhi/HamsterKombatBot{RESET_TEXT}")

akks = os.listdir(os.path.abspath("./sessions"))
proxyes = open("proxy.txt", "r").readlines()
json_file = open('profiles.json', 'r').read()
file = json.loads(json_file)

main_file = json.dumps(file['main'])

# Ensure 'output_json_file' variable is defined
output_json_file = 'profiles.json'  # Replace with your file name

for i in range(len(akks)):
    main_file_js = json.loads(main_file)
    proxy_index = i % len(proxyes)  # Use % operator for cyclic proxy usage
    proxy = proxyes[proxy_index].rstrip()
    
    # Check for the presence of 'http://'
    if not proxy.startswith('http://'):
        proxy = 'http://' + proxy
    
    main_file_js['proxy'] = proxy
    main_file_js['headers']['User-Agent'] = UserAgent(os='android').random
    session_name = akks[i].replace('.session', '')
    file[session_name] = main_file_js

# Open file for writing with UTF-8 encoding
with open(output_json_file, 'w', encoding='utf-8') as output_file:
    json.dump(file, output_file, ensure_ascii=False, indent=2)

print(f'{RESET_TEXT}Data successfully saved to file: {output_json_file}')
