#!/usr/bin/env python3
"""
DefaultPalWorldSettings.ini to YAML Converter
Automatically generates palworld_settings section for default.yaml from DefaultPalWorldSettings.ini

Usage:
    python3 ini_to_yaml_converter.py [input_file] [output_file]
    
Arguments:
    input_file: Path to DefaultPalWorldSettings.ini (optional, auto-detects if not provided)
    output_file: Output YAML file path (optional, prints to stdout if not provided)
"""

import os
import re
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, Tuple


class INIToYAMLConverter:
    """Converts DefaultPalWorldSettings.ini to YAML palworld_settings section"""
    
    def __init__(self):
        self.logger_enabled = True
    
    def log(self, message: str, level: str = "INFO"):
        """Simple logging function"""
        if self.logger_enabled:
            print(f"[{level}] {message}", file=sys.stderr)
    
    def find_default_ini_file(self) -> Optional[Path]:
        """
        Find DefaultPalWorldSettings.ini in common locations
        
        Returns:
            Path to DefaultPalWorldSettings.ini or None if not found
        """
        possible_paths = [
            # Current directory
            Path("./DefaultPalWorldSettings.ini"),
            
            # Common Palworld server locations
            Path("./palworld_server/DefaultPalWorldSettings.ini"),
            Path("/home/steam/palworld_server/DefaultPalWorldSettings.ini"),
            
            # Steam common locations
            Path("~/.steam/steamapps/common/PalServer/DefaultPalWorldSettings.ini").expanduser(),
            Path("~/steamapps/common/PalServer/DefaultPalWorldSettings.ini").expanduser(),
            
            # Config directory
            Path("./config/DefaultPalWorldSettings.ini"),
            
            # Relative paths
            Path("../palworld_server/DefaultPalWorldSettings.ini"),
            Path("../../palworld_server/DefaultPalWorldSettings.ini"),
        ]
        
        for path in possible_paths:
            if path.exists() and path.is_file():
                self.log(f"Found DefaultPalWorldSettings.ini at: {path}")
                return path
        
        return None
    
    def parse_ini_file(self, ini_path: Path) -> Dict[str, str]:
        """
        Parse DefaultPalWorldSettings.ini and extract OptionSettings
        
        Args:
            ini_path: Path to the INI file
            
        Returns:
            Dictionary of setting name -> value
        """
        try:
            # Try UTF-8 first
            content = ini_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            try:
                # Try UTF-8 with BOM
                content = ini_path.read_text(encoding='utf-8-sig')
                self.log("Used UTF-8-sig encoding due to BOM")
            except UnicodeDecodeError:
                # Try other encodings
                for encoding in ['latin1', 'cp1252']:
                    try:
                        content = ini_path.read_text(encoding=encoding)
                        self.log(f"Used {encoding} encoding")
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    raise ValueError("Could not decode INI file with any supported encoding")
        
        # Extract OptionSettings
        return self._extract_option_settings(content)
    
    def _extract_option_settings(self, content: str) -> Dict[str, str]:
        """
        Extract OptionSettings values from file content
        
        Args:
            content: File content as string
            
        Returns:
            Dictionary of setting name -> value
        """
        settings = {}
        
        # Find OptionSettings=(...) pattern
        pattern = r'OptionSettings=\(([^)]+)\)'
        match = re.search(pattern, content, re.DOTALL)
        
        if not match:
            raise ValueError("Could not find OptionSettings in INI file")
        
        options_content = match.group(1)
        
        # Parse individual settings (handle nested parentheses and complex values)
        settings_pattern = r'(\w+)=([^,)]+(?:\([^)]*\))?[^,)]*)'
        settings_matches = re.findall(settings_pattern, options_content)
        
        for setting_name, setting_value in settings_matches:
            cleaned_value = self._clean_setting_value(setting_value.strip())
            settings[setting_name] = cleaned_value
        
        self.log(f"Extracted {len(settings)} settings from OptionSettings")
        return settings
    
    def _clean_setting_value(self, value: str) -> str:
        """Clean and normalize setting values"""
        # Remove surrounding quotes
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        
        # Handle trailing commas and semicolons
        value = value.rstrip(',;')
        
        return value
    
    def _convert_to_env_var_name(self, setting_name: str) -> str:
        """
        Convert camelCase setting name to SNAKE_CASE environment variable name
        
        Args:
            setting_name: Original setting name (e.g., ServerName, bEnablePlayerToPlayerDamage)
            
        Returns:
            Environment variable name (e.g., SERVER_NAME, B_ENABLE_PLAYER_TO_PLAYER_DAMAGE)
        """
        # Handle boolean prefix 'b' specially
        if setting_name.startswith('b') and len(setting_name) > 1 and setting_name[1].isupper():
            # bEnablePlayerToPlayerDamage -> B_ENABLE_PLAYER_TO_PLAYER_DAMAGE
            remainder = setting_name[1:]
            env_name = 'B_' + self._camel_to_snake(remainder)
        else:
            # ServerName -> SERVER_NAME
            env_name = self._camel_to_snake(setting_name)
        
        return env_name.upper()
    
    def _camel_to_snake(self, camel_str: str) -> str:
        """Convert camelCase to snake_case"""
        # Insert underscore before uppercase letters (except first char)
        s1 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', camel_str)
        # Handle sequences of uppercase letters
        s2 = re.sub('([A-Z])([A-Z][a-z])', r'\1_\2', s1)
        return s2.upper()
    
    def _infer_data_type_and_format(self, value: str) -> Tuple[str, Any]:
        """
        Infer data type and format value appropriately for YAML
        
        Args:
            value: String value from INI
            
        Returns:
            Tuple of (yaml_formatted_value, default_value)
        """
        # Boolean values
        if value.lower() in ['true', 'false']:
            return f"${{{self._convert_to_env_var_name('temp')}:{value.lower()}}}", value.lower() == 'true'
        
        # Numeric values
        try:
            # Try integer first
            int_val = int(value)
            return f"${{{self._convert_to_env_var_name('temp')}:{int_val}}}", int_val
        except ValueError:
            try:
                # Try float
                float_val = float(value)
                return f"${{{self._convert_to_env_var_name('temp')}:{float_val}}}", float_val
            except ValueError:
                pass
        
        # String values (including None, empty strings, complex values)
        if value in ['None', '']:
            return f'"${{{self._convert_to_env_var_name("temp")}:{value}}}"', value
        else:
            return f'"${{{self._convert_to_env_var_name("temp")}:{value}}}"', value
    
    def generate_yaml_content(self, settings: Dict[str, str]) -> str:
        """
        Generate YAML palworld_settings section
        
        Args:
            settings: Dictionary of setting name -> value
            
        Returns:
            YAML content string
        """
        yaml_lines = ["# Direct Palworld settings (INI key names for automatic conversion)"]
        yaml_lines.append("palworld_settings:")
        
        # Group settings by category for better organization
        categories = self._categorize_settings(settings)
        
        for category_name, category_settings in categories.items():
            if category_settings:  # Only add non-empty categories
                yaml_lines.append(f"    # {category_name}")
                
                for setting_name in sorted(category_settings):
                    value = settings[setting_name]
                    env_var_name = self._convert_to_env_var_name(setting_name)
                    yaml_format, _ = self._infer_data_type_and_format(value)
                    
                    # Replace temp placeholder with actual env var name
                    yaml_format = yaml_format.replace(self._convert_to_env_var_name('temp'), env_var_name)
                    
                    yaml_lines.append(f"    {setting_name}: {yaml_format}")
                
                yaml_lines.append("")  # Empty line between categories
        
        return "\n".join(yaml_lines)
    
    def _categorize_settings(self, settings: Dict[str, str]) -> Dict[str, list]:
        """
        Categorize settings for better YAML organization
        
        Args:
            settings: Dictionary of setting name -> value
            
        Returns:
            Dictionary of category name -> list of setting names
        """
        categories = {
            "Core server settings": [],
            "API and RCON settings": [],
            "Authentication and region": [],
            "Game difficulty and mode": [],
            "Randomizer settings": [],
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
            "Loss and hardcore settings": [],
            "Logging and monitoring": [],
            "Special events and features": [],
            "Platform settings": [],
            "Global Palbox settings": [],
            "Network settings": [],
            "Other settings": []
        }
        
        # Categorization rules
        categorization_rules = {
            # Core server settings
            ("ServerName", "ServerDescription", "AdminPassword", "ServerPassword", 
             "PublicPort", "PublicIP", "ServerPlayerMaxNum", "CoopPlayerMaxNum"): "Core server settings",
            
            # API and RCON settings
            ("RESTAPIEnabled", "RESTAPIPort", "RCONEnabled", "RCONPort"): "API and RCON settings",
            
            # Authentication and region
            ("bUseAuth", "Region", "BanListURL"): "Authentication and region",
            
            # Game difficulty and mode
            ("Difficulty", "bIsMultiplay", "bIsPvP", "bHardcore", "DeathPenalty"): "Game difficulty and mode",
            
            # Randomizer settings
            ("RandomizerType", "RandomizerSeed", "bIsRandomizerPalLevelRandom"): "Randomizer settings",
            
            # Time and experience rates
            ("DayTimeSpeedRate", "NightTimeSpeedRate", "ExpRate", "WorkSpeedRate"): "Time and experience rates",
            
            # Pal settings
            ("PalCaptureRate", "PalSpawnNumRate", "PalDamageRateAttack", "PalDamageRateDefense",
             "PalStomachDecreaceRate", "PalStaminaDecreaceRate", "PalAutoHPRegeneRate", 
             "PalAutoHpRegeneRateInSleep", "PalEggDefaultHatchingTime"): "Pal settings",
            
            # Player settings
            ("PlayerDamageRateAttack", "PlayerDamageRateDefense", "PlayerStomachDecreaceRate",
             "PlayerStaminaDecreaceRate", "PlayerAutoHPRegeneRate", "PlayerAutoHpRegeneRateInSleep"): "Player settings",
            
            # PvP and combat settings
            ("bEnablePlayerToPlayerDamage", "bEnableFriendlyFire", "bEnableInvaderEnemy"): "PvP and combat settings",
            
            # Building and objects
            ("BuildObjectHpRate", "BuildObjectDamageRate", "BuildObjectDeteriorationDamageRate",
             "CollectionDropRate", "CollectionObjectHpRate", "CollectionObjectRespawnSpeedRate",
             "bBuildAreaLimit", "MaxBuildingLimitNum", "EnemyDropItemRate"): "Building and objects",
            
            # Base camp settings
            ("BaseCampMaxNum", "BaseCampWorkerMaxNum", "BaseCampMaxNumInGuild"): "Base camp settings",
            
            # Guild settings
            ("GuildPlayerMaxNum", "bAutoResetGuildNoOnlinePlayers", 
             "AutoResetGuildTimeNoOnlinePlayers"): "Guild settings",
            
            # Items and drops
            ("DropItemMaxNum", "DropItemMaxNum_UNKO", "DropItemAliveMaxHours", 
             "ItemWeightRate", "EquipmentDurabilityDamageRate"): "Items and drops",
            
            # Game mechanics
            ("bActiveUNKO", "bEnableAimAssistPad", "bEnableAimAssistKeyboard",
             "bCanPickupOtherGuildDeathPenaltyDrop", "bEnableNonLoginPenalty", "bEnableFastTravel",
             "bIsStartLocationSelectByMap", "bExistPlayerAfterLogout", "bEnableDefenseOtherGuildPlayer",
             "bInvisibleOtherGuildBaseCampAreaFX"): "Game mechanics",
            
            # Save and backup
            ("AutoSaveSpan", "bIsUseBackupSaveData"): "Save and backup",
            
            # Chat and communication
            ("bShowPlayerList", "ChatPostLimitPerMinute"): "Chat and communication",
            
            # Loss and hardcore settings
            ("bPalLost", "bCharacterRecreateInHardcore"): "Loss and hardcore settings",
            
            # Logging and monitoring
            ("LogFormatType",): "Logging and monitoring",
            
            # Special events and features
            ("SupplyDropSpan", "EnablePredatorBossPal"): "Special events and features",
            
            # Platform settings
            ("CrossplayPlatforms",): "Platform settings",
            
            # Global Palbox settings
            ("bAllowGlobalPalboxExport", "bAllowGlobalPalboxImport"): "Global Palbox settings",
            
            # Network settings
            ("ServerReplicatePawnCullDistance", "ItemContainerForceMarkDirtyInterval"): "Network settings",
        }
        
        # Apply categorization rules
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
        """
        Main conversion function
        
        Args:
            input_file: Input INI file path (auto-detect if None)
            output_file: Output YAML file path (stdout if None)
            
        Returns:
            Success status
        """
        try:
            # Find input file
            if input_file is None:
                input_file = self.find_default_ini_file()
                if input_file is None:
                    self.log("ERROR: Could not find DefaultPalWorldSettings.ini", "ERROR")
                    self.log("Please specify the input file path or place DefaultPalWorldSettings.ini in current directory", "ERROR")
                    return False
            elif not input_file.exists():
                self.log(f"ERROR: Input file not found: {input_file}", "ERROR")
                return False
            
            # Parse INI file
            self.log(f"Parsing INI file: {input_file}")
            settings = self.parse_ini_file(input_file)
            
            if not settings:
                self.log("ERROR: No settings found in INI file", "ERROR")
                return False
            
            # Generate YAML content
            self.log("Generating YAML content...")
            yaml_content = self.generate_yaml_content(settings)
            
            # Output result
            if output_file:
                output_file.write_text(yaml_content, encoding='utf-8')
                self.log(f"YAML content written to: {output_file}")
            else:
                print(yaml_content)
            
            self.log(f"SUCCESS: Converted {len(settings)} settings from INI to YAML format")
            return True
            
        except Exception as e:
            self.log(f"ERROR: Conversion failed: {e}", "ERROR")
            return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Convert DefaultPalWorldSettings.ini to YAML palworld_settings section",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Auto-detect INI file and output to stdout
    python3 ini_to_yaml_converter.py
    
    # Specify input file, output to stdout
    python3 ini_to_yaml_converter.py ./DefaultPalWorldSettings.ini
    
    # Specify both input and output files
    python3 ini_to_yaml_converter.py ./DefaultPalWorldSettings.ini ./palworld_settings.yaml
    
    # Redirect stdout to file
    python3 ini_to_yaml_converter.py > palworld_settings.yaml
        """
    )
    
    parser.add_argument('input_file', nargs='?', help='Path to DefaultPalWorldSettings.ini (auto-detect if not provided)')
    parser.add_argument('output_file', nargs='?', help='Output YAML file path (stdout if not provided)')
    parser.add_argument('--quiet', '-q', action='store_true', help='Suppress log messages')
    
    args = parser.parse_args()
    
    # Create converter
    converter = INIToYAMLConverter()
    converter.logger_enabled = not args.quiet
    
    # Convert file paths to Path objects
    input_file = Path(args.input_file) if args.input_file else None
    output_file = Path(args.output_file) if args.output_file else None
    
    # Run conversion
    success = converter.convert(input_file, output_file)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
