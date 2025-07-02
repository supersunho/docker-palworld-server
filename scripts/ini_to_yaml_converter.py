#!/usr/bin/env python3
"""
DefaultPalWorldSettings.ini to YAML Converter
Converts INI settings to YAML format with environment variables
"""

import os
import re
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List


class INIParsingError(Exception):
    """Custom exception for INI parsing errors"""
    pass


class FileEncodingError(Exception):
    """Custom exception for file encoding errors"""
    pass


class INIToYAMLConverter:
    """Converts DefaultPalWorldSettings.ini to YAML palworld_settings section"""
    
    def __init__(self):
        self.logger_enabled = True
        self.supported_encodings = ['utf-8', 'utf-8-sig', 'latin1', 'cp1252', 'iso-8859-1']
    
    def log(self, message: str, level: str = "INFO"):
        """Simple logging function"""
        if self.logger_enabled:
            level_emoji = {
                "INFO": "ℹ️",
                "ERROR": "❌", 
                "DEBUG": "🔍",
                "SUCCESS": "✅",
                "WARNING": "⚠️"
            }
            emoji = level_emoji.get(level, "ℹ️")
            print(f"{emoji} [{level}] {message}", file=sys.stderr)
    
    def find_default_ini_file(self) -> Optional[Path]:
        """Find DefaultPalWorldSettings.ini in common locations"""
        possible_paths = [
            Path("./DefaultPalWorldSettings.ini"),
            Path("./palworld_server/DefaultPalWorldSettings.ini"),
            Path("/home/steam/palworld_server/DefaultPalWorldSettings.ini"),
            Path("~/.steam/steamapps/common/PalServer/DefaultPalWorldSettings.ini").expanduser(),
            Path("~/steamapps/common/PalServer/DefaultPalWorldSettings.ini").expanduser(),
            Path("./config/DefaultPalWorldSettings.ini"),
            Path("../palworld_server/DefaultPalWorldSettings.ini"),
            Path("../../palworld_server/DefaultPalWorldSettings.ini"),
        ]
        
        for path in possible_paths:
            try:
                if path.exists() and path.is_file():
                    if self._validate_ini_file(path):
                        self.log(f"Found DefaultPalWorldSettings.ini at: {path}")
                        return path
                    else:
                        self.log(f"Found file at {path} but validation failed", "WARNING")
            except (OSError, PermissionError) as e:
                self.log(f"Cannot access {path}: {e}", "WARNING")
                continue
        
        return None
    
    def _validate_ini_file(self, file_path: Path) -> bool:
        """Validate that the file is a valid Palworld settings INI"""
        try:
            if file_path.stat().st_size == 0:
                return False
            
            content = self._read_file_with_encoding_detection(file_path, max_bytes=1024)
            return 'OptionSettings=' in content and 'PalWorldSettings' in content
            
        except Exception:
            return False
    
    def parse_ini_file(self, ini_path: Path) -> Dict[str, str]:
        """Parse DefaultPalWorldSettings.ini and extract OptionSettings"""
        if not ini_path.exists():
            raise FileNotFoundError(f"INI file not found: {ini_path}")
        
        if not ini_path.is_file():
            raise ValueError(f"Path is not a file: {ini_path}")
        
        try:
            content = self._read_file_with_encoding_detection(ini_path)
            return self._extract_option_settings(content)
            
        except FileEncodingError as e:
            self.log(f"File encoding error: {e}", "ERROR")
            raise
        except INIParsingError as e:
            self.log(f"INI parsing error: {e}", "ERROR")
            raise
        except Exception as e:
            self.log(f"Unexpected error parsing INI file: {e}", "ERROR")
            raise INIParsingError(f"Failed to parse INI file: {e}")
    
    def _read_file_with_encoding_detection(self, file_path: Path, max_bytes: Optional[int] = None) -> str:
        """Read file with automatic encoding detection and enhanced error handling"""
        content = None
        used_encoding = None
        
        for encoding in self.supported_encodings:
            try:
                if max_bytes:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read(max_bytes)
                else:
                    content = file_path.read_text(encoding=encoding)
                
                used_encoding = encoding
                break
                
            except UnicodeDecodeError as e:
                self.log(f"Encoding {encoding} failed: {e}", "DEBUG")
                continue
            except (OSError, PermissionError) as e:
                raise FileEncodingError(f"Cannot read file {file_path}: {e}")
        
        if content is None:
            tried_encodings = ', '.join(self.supported_encodings)
            raise FileEncodingError(
                f"Could not decode file {file_path} with any supported encoding. "
                f"Tried: {tried_encodings}. "
                f"File may be corrupted or in an unsupported format."
            )
        
        if used_encoding != 'utf-8':
            self.log(f"Used {used_encoding} encoding for file reading", "WARNING")
        
        return content
    
    def _extract_option_settings(self, content: str) -> Dict[str, str]:
        """Extract OptionSettings values from file content"""
        if not content or len(content.strip()) == 0:
            raise INIParsingError("File content is empty")
        
        settings = {}
        
        try:
            pattern = r'OptionSettings=\((.*)\)'
            match = re.search(pattern, content, re.DOTALL)
            
            if not match:
                available_sections = re.findall(r'\[([^\]]+)\]', content)
                section_info = f"Available sections: {available_sections}" if available_sections else "No INI sections found"
                raise INIParsingError(
                    f"Could not find OptionSettings in INI file. {section_info}. "
                    f"This may not be a valid Palworld settings file."
                )
            
            options_content = match.group(1).strip()
            if not options_content:
                raise INIParsingError("OptionSettings section is empty")
            
            pairs = self._split_outside_parentheses(options_content)
            
            if not pairs:
                raise INIParsingError("No setting pairs found in OptionSettings")
            
            for pair in pairs:
                if not pair or '=' not in pair:
                    continue
                
                try:
                    key, value = pair.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if not key:
                        self.log(f"Empty key found in pair: {pair}", "WARNING")
                        continue
                    
                    cleaned_value = self._clean_setting_value(value)
                    settings[key] = cleaned_value
                    
                except Exception as e:
                    self.log(f"Error processing setting pair '{pair}': {e}", "WARNING")
                    continue
            
            if not settings:
                raise INIParsingError("No valid settings found in OptionSettings")
            
            self.log(f"Extracted {len(settings)} settings from OptionSettings", "SUCCESS")
            
        except INIParsingError:
            raise
        except Exception as e:
            raise INIParsingError(f"Failed to extract OptionSettings: {e}")
        
        return settings
    
    def _split_outside_parentheses(self, content: str) -> List[str]:
        """Split content by commas that are not inside parentheses"""
        if not content:
            return []
        
        parts = []
        current = []
        depth = 0
        
        for char in content:
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
            
            if char == ',' and depth == 0:
                part = ''.join(current).strip()
                if part:
                    parts.append(part)
                current = []
            else:
                current.append(char)
        
        if current:
            part = ''.join(current).strip()
            if part:
                parts.append(part)
        
        return parts
    
    def _clean_setting_value(self, value: str) -> str:
        """Clean and normalize setting values"""
        if not value:
            return value
        
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            value = value[1:-1]
        
        value = value.rstrip(',;')
        return value
    
    def _convert_to_env_var_name(self, setting_name: str) -> str:
        """Convert camelCase setting name to SNAKE_CASE environment variable name"""
        if not setting_name:
            return ""
        
        if setting_name.startswith('b') and len(setting_name) > 1 and setting_name[1].isupper():
            remainder = setting_name[1:]
            env_name = self._camel_to_snake(remainder)
        else:
            env_name = self._camel_to_snake(setting_name)
        
        return env_name.upper()
    
    def _camel_to_snake(self, camel_str: str) -> str:
        """Convert camelCase to snake_case with special abbreviation handling"""
        if not camel_str:
            return ""
        
        # Handle compound abbreviations and special cases first
        compound_replacements = {
            'RESTAPI': 'RESTAPI',  # Keep as single word
            'PvP': 'PVP',          # Player vs Player
            'PVP': 'PVP',          # Already correct
            'BanList': 'BANLIST',  # Keep as single word
            'AutoHP': 'AUTO_HP',   # Auto HP should have underscore
            'AutoHp': 'AUTO_HP',   # Auto HP variant
        }
        
        # Single abbreviations
        single_replacements = {
            'API': 'API',
            'RCON': 'RCON',
            'HTTP': 'HTTP',
            'URL': 'URL',
            'ID': 'ID',
            'HP': 'HP',
            'AI': 'AI',
            'UI': 'UI',
            'FPS': 'FPS',
            'CPU': 'CPU',
            'GPU': 'GPU',
            'RAM': 'RAM'
        }
        
        # Apply compound replacements first
        processed_str = camel_str
        for original, replacement in compound_replacements.items():
            processed_str = processed_str.replace(original, replacement)
        
        # Apply single replacements
        for original, replacement in single_replacements.items():
            processed_str = processed_str.replace(original, replacement)
        
        # Apply standard camelCase to snake_case conversion
        s1 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', processed_str)
        s2 = re.sub('([A-Z])([A-Z][a-z])', r'\1_\2', s1)
        
        return s2.upper()
    
    def _infer_data_type_and_format(self, value: str) -> Tuple[str, Any]:
        """Infer data type and format value appropriately for YAML"""
        if not value:
            return f'"${{{self._convert_to_env_var_name("temp")}:}}"', ""
        
        if value.lower() in ['true', 'false']:
            return f"${{{self._convert_to_env_var_name('temp')}:{value.lower()}}}", value.lower() == 'true'
        
        try:
            int_val = int(value)
            return f"${{{self._convert_to_env_var_name('temp')}:{int_val}}}", int_val
        except ValueError:
            try:
                float_val = float(value)
                return f"${{{self._convert_to_env_var_name('temp')}:{float_val}}}", float_val
            except ValueError:
                pass
        
        if value in ['None', '']:
            return f'"${{{self._convert_to_env_var_name("temp")}:{value}}}"', value
        else:
            return f'"${{{self._convert_to_env_var_name("temp")}:{value}}}"', value
    
    def generate_yaml_content(self, settings: Dict[str, str]) -> str:
        """Generate YAML palworld_settings section"""
        if not settings:
            raise ValueError("No settings provided for YAML generation")
        
        yaml_lines = ["palworld_settings:"]
        
        categories = self._categorize_settings(settings)
        
        for category_name, category_settings in categories.items():
            if category_settings:
                yaml_lines.append(f"    # {category_name}")
                
                for setting_name in sorted(category_settings):
                    try:
                        value = settings[setting_name]
                        env_var_name = self._convert_to_env_var_name(setting_name)
                        yaml_format, _ = self._infer_data_type_and_format(value)
                        
                        yaml_format = yaml_format.replace(self._convert_to_env_var_name('temp'), env_var_name)
                        yaml_lines.append(f"    {setting_name}: {yaml_format}")
                        
                    except Exception as e:
                        self.log(f"Error processing setting {setting_name}: {e}", "WARNING")
                        continue
                
                yaml_lines.append("")
        
        return "\n".join(yaml_lines)
    
    def _categorize_settings(self, settings: Dict[str, str]) -> Dict[str, list]:
        """Categorize settings for better YAML organization"""
        categories = {
            "Core server settings": [],
            "API and RCON settings": [],
            "Authentication and region": [],
            "Game difficulty and mode": [],
            "Time and experience rates": [],
            "Pal settings": [],
            "Player settings": [],
            "PvP and combat settings": [],
            "Building and objects": [],
            "Base camp settings": [],
            "Guild settings": [],
            "Items and drops": [],
            "Game mechanics": [],
            "Save and backup": [],
            "Chat and communication": [],
            "Platform settings": [],
            "Network settings": [],
            "Other settings": []
        }
        
        categorization_rules = {
            ("ServerName", "ServerDescription", "AdminPassword", "ServerPassword", 
             "PublicPort", "PublicIP", "ServerPlayerMaxNum", "CoopPlayerMaxNum"): "Core server settings",
            ("RESTAPIEnabled", "RESTAPIPort", "RCONEnabled", "RCONPort"): "API and RCON settings",
            ("bUseAuth", "Region", "BanListURL"): "Authentication and region",
            ("Difficulty", "bIsMultiplay", "bIsPvP", "bHardcore", "DeathPenalty"): "Game difficulty and mode",
            ("DayTimeSpeedRate", "NightTimeSpeedRate", "ExpRate", "WorkSpeedRate"): "Time and experience rates",
            ("PalCaptureRate", "PalSpawnNumRate", "PalDamageRateAttack", "PalDamageRateDefense",
             "PalStomachDecreaceRate", "PalStaminaDecreaceRate", "PalAutoHPRegeneRate", 
             "PalAutoHpRegeneRateInSleep", "PalEggDefaultHatchingTime"): "Pal settings",
            ("PlayerDamageRateAttack", "PlayerDamageRateDefense", "PlayerStomachDecreaceRate",
             "PlayerStaminaDecreaceRate", "PlayerAutoHPRegeneRate", "PlayerAutoHpRegeneRateInSleep"): "Player settings",
            ("bEnablePlayerToPlayerDamage", "bEnableFriendlyFire", "bEnableInvaderEnemy"): "PvP and combat settings",
            ("BuildObjectHpRate", "BuildObjectDamageRate", "BuildObjectDeteriorationDamageRate",
             "CollectionDropRate", "CollectionObjectHpRate", "CollectionObjectRespawnSpeedRate",
             "bBuildAreaLimit", "MaxBuildingLimitNum", "EnemyDropItemRate"): "Building and objects",
            ("BaseCampMaxNum", "BaseCampWorkerMaxNum", "BaseCampMaxNumInGuild"): "Base camp settings",
            ("GuildPlayerMaxNum", "bAutoResetGuildNoOnlinePlayers", 
             "AutoResetGuildTimeNoOnlinePlayers"): "Guild settings",
            ("DropItemMaxNum", "DropItemMaxNum_UNKO", "DropItemAliveMaxHours", 
             "ItemWeightRate", "EquipmentDurabilityDamageRate"): "Items and drops",
            ("bActiveUNKO", "bEnableAimAssistPad", "bEnableAimAssistKeyboard",
             "bCanPickupOtherGuildDeathPenaltyDrop", "bEnableNonLoginPenalty", "bEnableFastTravel",
             "bIsStartLocationSelectByMap", "bExistPlayerAfterLogout", "bEnableDefenseOtherGuildPlayer",
             "bInvisibleOtherGuildBaseCampAreaFX"): "Game mechanics",
            ("AutoSaveSpan", "bIsUseBackupSaveData"): "Save and backup",
            ("bShowPlayerList", "ChatPostLimitPerMinute"): "Chat and communication",
            ("CrossplayPlatforms",): "Platform settings",
            ("ServerReplicatePawnCullDistance", "ItemContainerForceMarkDirtyInterval"): "Network settings",
        }
        
        for setting_name in settings.keys():
            categorized = False
            for setting_group, category in categorization_rules.items():
                if setting_name in setting_group:
                    categories[category].append(setting_name)
                    categorized = True
                    break
            
            if not categorized:
                categories["Other settings"].append(setting_name)
        
        return categories
    
    def convert(self, input_file: Optional[Path] = None, output_file: Optional[Path] = None) -> bool:
        """Main conversion function with enhanced error handling"""
        try:
            if input_file is None:
                input_file = self.find_default_ini_file()
                if input_file is None:
                    self.log("Could not find DefaultPalWorldSettings.ini", "ERROR")
                    self.log("Searched common locations. Please specify input file path.", "ERROR")
                    return False
            
            if not input_file.exists():
                self.log(f"Input file not found: {input_file}", "ERROR")
                return False
            
            self.log(f"Parsing INI file: {input_file}")
            settings = self.parse_ini_file(input_file)
            
            if not settings:
                self.log("No settings found in INI file", "ERROR")
                return False
            
            yaml_content = self.generate_yaml_content(settings)
            
            if output_file:
                try:
                    output_file.parent.mkdir(parents=True, exist_ok=True)
                    output_file.write_text(yaml_content, encoding='utf-8')
                    self.log(f"YAML content written to: {output_file}", "SUCCESS")
                except (OSError, PermissionError) as e:
                    self.log(f"Cannot write to output file {output_file}: {e}", "ERROR")
                    return False
            else:
                print(yaml_content)
            
            self.log(f"Converted {len(settings)} settings to YAML format", "SUCCESS")
            return True
            
        except (FileEncodingError, INIParsingError) as e:
            self.log(f"Conversion failed: {e}", "ERROR")
            return False
        except Exception as e:
            self.log(f"Unexpected error during conversion: {e}", "ERROR")
            return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Convert DefaultPalWorldSettings.ini to YAML palworld_settings section"
    )
    
    parser.add_argument('input_file', nargs='?', help='Path to DefaultPalWorldSettings.ini')
    parser.add_argument('output_file', nargs='?', help='Output YAML file path')
    parser.add_argument('--quiet', '-q', action='store_true', help='Suppress log messages')
    
    args = parser.parse_args()
    
    converter = INIToYAMLConverter()
    converter.logger_enabled = not args.quiet
    
    input_file = Path(args.input_file) if args.input_file else None
    output_file = Path(args.output_file) if args.output_file else None
    
    success = converter.convert(input_file, output_file)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
