# translate_srt.py
# v0.12
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# https://github.com/FlyingFathead/srt-translate-OpenAI-API
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

from openai import OpenAI
import pysrt
import sys
import os
import configparser
import shutil

# Initialize and read the configuration
config = configparser.ConfigParser()
config.read('config.ini')

# Defining a unique marker
marker = " <|> "  # Choose a unique sequence that won't appear in translations.

# print term width horizontal line
def print_horizontal_line(character='-'):
    terminal_width = shutil.get_terminal_size().columns
    line = character * terminal_width
    print(line, flush=True)

# Function to read the OpenAI API key securely
def get_api_key():
    prefer_env = config.getboolean('DEFAULT', 'PreferEnvForAPIKey', fallback=True)

    if prefer_env:
        api_key = os.getenv('OPENAI_API_KEY')
        if api_key is not None:
            return api_key

    try:
        with open('api_token.txt', 'r') as file:
            return file.read().strip()
    except FileNotFoundError:
        if not prefer_env:
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key is not None:
                return api_key

        print("The OPENAI_API_KEY environment variable is not set, and `api_token.txt` was not found.")
        print("Please set either one and adjust `config.ini` if needed for the preferred load order.")
        sys.exit(1)

# Read the config.ini / configuration
def get_config(section, option, prompt_message, is_int=False):
    if section not in config or option not in config[section]:
        print(prompt_message)
        value = input().strip()
        if not section in config:
            config.add_section(section)
        config.set(section, option, value)
        with open('config.ini', 'w') as configfile:
            config.write(configfile)
        return int(value) if is_int else value
    return int(config[section][option]) if is_int else config[section][option]

# Function to split long lines without breaking words
def split_long_line(text, max_line_length):
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        if sum(len(w) + 1 for w in current_line) + len(word) <= max_line_length:
            current_line.append(word)
        else:
            lines.append(' '.join(current_line))
            current_line = [word]
    if current_line:
        lines.append(' '.join(current_line))
    return lines

# Check for the correct usage and provide feedback if needed
if len(sys.argv) != 2:
    print("Usage: python translate_srt.py path/to/your/file.srt")
    sys.exit(1)

# Check the .srt file and load it in
input_file_path = sys.argv[1]
if not input_file_path.lower().endswith('.srt'):
    print("The provided file does not have an .srt extension.")
    sys.exit(1)

# Load in the .srt file
try:
    subs = pysrt.open(input_file_path)
except Exception as e:
    print(f"Error reading the SRT file: {e}")
    sys.exit(1)

# Determine the output file name based on the input
output_file_path = input_file_path.replace('.srt', '_translated.srt')

# Check if the output file already exists
if os.path.exists(output_file_path):
    print(f"Warning: The file {output_file_path} already exists.")
    overwrite = input("Do you want to overwrite it? (y/n): ").lower().strip()
    while overwrite not in ['y', 'n']:
        overwrite = input("Please enter 'y' or 'n': ").lower().strip()

    if overwrite == 'n':
        print("Translation canceled. No files were overwritten.")
        sys.exit(0)

# Initialize the OpenAI client
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Configuration retrievals
try:
    # Here, no is_int argument is necessary because it defaults to False.
    default_translation_language = get_config('Translation', 'DefaultLanguage', "Please enter the default translation language code (e.g., 'es' for Spanish):")
    # For string values, even though is_int defaults to False, it's okay to specify it explicitly for clarity.
    additional_info = get_config('Translation', 'AdditionalInfo', "Enter any additional info for translation context (leave blank if none):", is_int=False)
    # For integer values, explicitly specify is_int=True.
    block_size = get_config('Settings', 'BlockSize', "Please enter the number of subtitles to process at once (e.g., 10):", is_int=True)
    max_line_length = get_config('Settings', 'MaxLineLength', "Max characters per subtitle line:", is_int=True)
    # For string values again, no need to specify is_int.
    model = get_config('Settings', 'Model', "Please enter the model to use (e.g., 'gpt-3.5-turbo-0125'):")
    # Here is_int is not needed as temperature is not an integer.
    temperature = get_config('Settings', 'Temperature', "Please enter the temperature to use for translation (e.g., 0.3):")
    # Explicitly specify is_int=True for integer values.
    max_tokens = get_config('Settings', 'MaxTokens', "Please enter the max tokens to use for translation (e.g., 1024):", is_int=True)
except Exception as e:
    print(f"Error retrieving configuration: {e}")
    sys.exit(1)

# Function to translate blocks of subtitles with context-specific information
def translate_block(block, block_num, total_blocks):
    print_horizontal_line()
    print(f"::: [ Translating block {block_num} / {total_blocks} ]")

    # Format subtitles into a block with index prefixes
    combined_text = "\n".join([f"[{sub.index}] {sub.text}".replace('\n', ' ') for sub in block])
    
    print("::: Input text:")
    print_horizontal_line()
    print(combined_text)

    # Translation prompt remains the same.
    if additional_info:
        prompt_text = f"{additional_info} Translate this into {default_translation_language}: {combined_text}"
    else:
        prompt_text = f"Translate this into {default_translation_language}: {combined_text}"

    # API call and translation processing remains the same.
    try:
        chat_completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": prompt_text}],
            temperature=float(temperature),
            max_tokens=max_tokens
        )
        translated_text = chat_completion.choices[0].message.content.strip()

        print_horizontal_line()
        print("::: Translated text (verify indexes):")
        print_horizontal_line()
        print(translated_text)

    except Exception as e:
        print(f"Error during API call: {e}")
        sys.exit(1)

    # Splitting based on newline characters and index prefixes, then extracting the text.
    indexed_translations = [line[line.find(']') + 2:] for line in translated_text.split("\n") if line.strip()]
    
    return indexed_translations

# In the main translation loop:
total_blocks = (len(subs) + block_size - 1) // block_size

# Translate block by block
try:
    for i, start in enumerate(range(0, len(subs), block_size)):
        block = subs[start:start + block_size]
        translated_block = translate_block(block, i + 1, total_blocks)
        for j, sub in enumerate(block):
            if j < len(translated_block):
                # Apply line splitting only if max_line_length is greater than zero.
                if max_line_length > 0:
                    split_text = split_long_line(translated_block[j], max_line_length)
                    sub.text = '\n'.join(split_text)
                else:
                    # If max_line_length is zero, use the text without splitting.
                    sub.text = translated_block[j]
            else:
                sub.text = "Translation Error"
except Exception as e:
    print(f"Error during translation process: {e}")
    sys.exit(1)

# Save the translated subtitles
subs.save(output_file_path)
print_horizontal_line()
print(f"::: Translation done!\n::: Translated subtitles saved to: {output_file_path}")
print_horizontal_line()


# ~~~
# old
# ~~~

# old method for translation blocks
""" # Function to translate blocks of subtitles with context-specific information
def translate_block(block, block_num, total_blocks):
    print_horizontal_line()
    print(f"::: [ Translating block {block_num} / {total_blocks} ]")
    combined_text = marker.join([sub.text for sub in block])
    print("::: Input text:")
    print_horizontal_line()
    print(combined_text)

    if additional_info:
        prompt_text = f"{additional_info} Translate this into {default_translation_language}: {combined_text}"
    else:
        prompt_text = f"Translate this into {default_translation_language}: {combined_text}"

    try:
        chat_completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": prompt_text}],
            temperature=float(temperature),
            max_tokens=max_tokens
        )

        # Accessing the translated text correctly
        translated_text = chat_completion.choices[0].message.content.strip()

        # Debug: Print the translated text to verify marker integrity
        print_horizontal_line()
        print("::: Translated text (verify markers):")
        print_horizontal_line()
        print(translated_text)

    except Exception as e:
        print(f"Error during API call: {e}")
        sys.exit(1)

    # Verify the integrity of the marker post-translation
    if marker not in translated_text:
        print("Warning: Marker integrity compromised post-translation.")
        # Handle this case appropriately, perhaps by flagging or manual review.

    return translated_text.split(marker) """