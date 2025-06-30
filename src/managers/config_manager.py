#!/usr/bin/env python3
"""
Configuration file management for Palworld server
Handles PalWorldSettings.ini and Engine.ini generation with automatic conversion and fallback support
"""

import re
from pathlib import Path
from typing import Dict, Any
from dataclasses import asdict

from ..config_loader import PalworldConfig
from ..logging_setup import log_server_event


class ConfigManager:
    """Server configuration file management with automatic INI conversion and fallback support"""
    
    def __init__(self, config: PalworldConfig, logger):
        self.config = config
        self.logger = logger
        self.server_path = config.paths.server_dir
        self.config_dir = self.server_path / "Pal" / "Saved" / "Config" / "LinuxServer"
        
        # Sample files paths for automatic parsing
        self.default_settings_path = self.server_path / "DefaultPalWorldSettings.ini"
        self.default_engine_path = self.server_path / "DefaultEngine.ini"
        
        # Cache for parsed defaults
        self._default_settings_cache = None
    
    def generate_server_settings(self) -> bool:
        """Generate Palworld server settings file using automatic conversion with fallback"""
        try:
            settings_file = self.config_dir / "PalWorldSettings.ini"
            
            # Ensure directory exists
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate settings content using automatic conversion with fallback
            settings_content = self._generate_settings_content_auto()
            
            settings_file.write_text(settings_content, encoding='utf-8')
            
            log_server_event(self.logger, "config_generate", 
                           "Server settings file generated successfully", 
                           settings_file=str(settings_file))
            return True
            
        except Exception as e:
            log_server_event(self.logger, "config_generate_fail", 
                           f"Failed to generate settings file: {e}")
            return False
    
    def generate_engine_settings(self) -> bool:
        """Generate Palworld engine settings file with sample file parsing and fallback"""
        try:
            engine_file = self.config_dir / "Engine.ini"
            
            # Ensure directory exists
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate engine content using sample file + performance settings
            engine_content = self._generate_engine_content()
            
            engine_file.write_text(engine_content, encoding='utf-8')
            
            log_server_event(self.logger, "config_generate", 
                           "Engine settings file generated successfully", 
                           engine_file=str(engine_file))
            return True
            
        except Exception as e:
            log_server_event(self.logger, "config_generate_fail", 
                           f"Failed to generate engine settings file: {e}")
            return False
    
    def _generate_settings_content_auto(self) -> str:
        """
        Generate settings content using automatic conversion with fallback
        
        Returns:
            Complete PalWorldSettings.ini content
        """
        try:
            # Try to get defaults from DefaultPalWorldSettings.ini
            defaults = self._get_default_settings()
            
            # Check if we successfully parsed any defaults
            if not defaults:
                self.logger.warning("No default settings found, falling back to legacy method")
                return self._generate_settings_content_legacy()
            
            # Get user settings from palworld_settings (automatic key matching!)
            user_settings = {}
            palworld_settings_dict = asdict(self.config.palworld_settings)
            
            for key, value in palworld_settings_dict.items():
                user_settings[key] = self._format_ini_value(value)
            
            # Merge defaults with user overrides
            final_settings = {**defaults, **user_settings}
            
            # Log overrides for debugging
            override_count = 0
            new_setting_count = 0
            for key, value in user_settings.items():
                if key in defaults and defaults[key] != value:
                    self.logger.debug(f"Override applied: {key}={value} (was {defaults[key]})")
                    override_count += 1
                elif key not in defaults:
                    self.logger.info(f"New setting added: {key}={value}")
                    new_setting_count += 1
            
            self.logger.info(f"Auto settings generation successful: {len(defaults)} defaults, "
                           f"{override_count} overrides, {new_setting_count} new settings")
            
            # Convert to INI format
            return self._dict_to_ini_optionsettings(final_settings)
            
        except Exception as e:
            # Fallback to legacy method if anything goes wrong
            self.logger.error(f"Auto settings generation failed: {e}")
            self.logger.info("Falling back to legacy settings generation")
            return self._generate_settings_content_legacy()
    
    def _get_default_settings(self) -> Dict[str, str]:
        """Get cached default settings from DefaultPalWorldSettings.ini"""
        if self._default_settings_cache is None:
            self._default_settings_cache = self._parse_default_settings()
        return self._default_settings_cache
    
    def _parse_default_settings(self) -> Dict[str, str]:
        """
        Parse DefaultPalWorldSettings.ini with comprehensive error handling
        
        Returns:
            Dictionary of setting name -> default value
        """
        # Try multiple possible locations for sample file
        possible_paths = [
            self.default_settings_path,
            self.server_path / "Pal" / "DefaultPalWorldSettings.ini",
            Path(__file__).parent.parent.parent / "config" / "DefaultPalWorldSettings.ini"
        ]
        
        for sample_path in possible_paths:
            if sample_path.exists():
                try:
                    content = sample_path.read_text(encoding='utf-8')
                    defaults = self._extract_option_settings(content)
                    
                    if defaults:  # Only return if we actually parsed something
                        self.logger.info(f"Parsed {len(defaults)} default settings from: {sample_path}")
                        return defaults
                    else:
                        self.logger.warning(f"No valid settings found in: {sample_path}")
                        
                except UnicodeDecodeError as e:
                    # Handle BOM issues
                    self.logger.warning(f"Unicode decode error in {sample_path}: {e}")
                    try:
                        # Try with BOM handling
                        content = sample_path.read_text(encoding='utf-8-sig')
                        defaults = self._extract_option_settings(content)
                        if defaults:
                            self.logger.info(f"Parsed {len(defaults)} settings after BOM handling: {sample_path}")
                            return defaults
                    except Exception as bom_e:
                        self.logger.warning(f"BOM handling also failed for {sample_path}: {bom_e}")
                        
                except Exception as e:
                    self.logger.warning(f"Failed to parse {sample_path}: {e}")
                    continue
        
        # Return empty dict if all parsing attempts failed
        self.logger.warning("No DefaultPalWorldSettings.ini found or parsed successfully")
        return {}
    
    def _extract_option_settings(self, content: str) -> Dict[str, str]:
        """
        Extract OptionSettings values from DefaultPalWorldSettings.ini content
        
        Args:
            content: File content as string
            
        Returns:
            Dictionary of setting name -> value
        """
        defaults = {}
        
        try:
            # Find OptionSettings=(...) pattern
            pattern = r'OptionSettings=\(([^)]+)\)'
            match = re.search(pattern, content, re.DOTALL)
            
            if not match:
                self.logger.error("Could not find OptionSettings in default file")
                return defaults
            
            options_content = match.group(1)
            
            # Parse individual settings (handle nested parentheses)
            settings_pattern = r'(\w+)=([^,)]+(?:\([^)]*\))?[^,)]*)'
            settings_matches = re.findall(settings_pattern, options_content)
            
            for setting_name, setting_value in settings_matches:
                # Clean up the value (remove quotes, handle booleans)
                cleaned_value = self._clean_setting_value(setting_value.strip())
                defaults[setting_name] = cleaned_value
            
            self.logger.debug(f"Successfully extracted {len(defaults)} settings from OptionSettings")
            
        except Exception as e:
            self.logger.error(f"Failed to extract OptionSettings: {e}")
        
        return defaults
    
    def _clean_setting_value(self, value: str) -> str:
        """
        Clean and normalize setting values
        
        Args:
            value: Raw setting value
            
        Returns:
            Cleaned setting value
        """
        # Remove surrounding quotes
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        
        # Handle special cases
        if value == "None":
            return "None"
        elif value.lower() in ["true", "false"]:
            return value.capitalize()
        
        return value
    
    def _format_ini_value(self, value) -> str:
        """
        Format Python value for INI file
        
        Args:
            value: Python value to format
            
        Returns:
            INI-formatted value string
        """
        if isinstance(value, bool):
            return str(value).capitalize()  # True/False
        elif isinstance(value, str):
            return f'"{value}"' if value else '""'
        elif isinstance(value, (int, float)):
            return str(value)
        else:
            return str(value)
    
    def _dict_to_ini_optionsettings(self, settings: Dict[str, str]) -> str:
        """
        Convert settings dictionary to INI OptionSettings format
        
        Args:
            settings: Dictionary of setting name -> value
            
        Returns:
            Complete INI file content
        """
        settings_list = []
        for key, value in settings.items():
            settings_list.append(f"{key}={value}")
        
        return f"""[/Script/Pal.PalGameWorldSettings]
OptionSettings=({','.join(settings_list)})"""
    
    def _generate_settings_content_legacy(self) -> str:
        """
        Legacy settings generation method (fallback for when auto method fails)
        Used when palworld_settings parsing fails or DefaultPalWorldSettings.ini is unavailable
        """
        self.logger.info("Using legacy settings generation method")
        
        server_cfg = self.config.server
        api_cfg = self.config.rest_api
        rcon_cfg = self.config.rcon
        gameplay_cfg = self.config.gameplay
        items_cfg = self.config.items
        base_camp_cfg = self.config.base_camp
        guild_cfg = self.config.guild
        pal_cfg = self.config.pal_settings
        building_cfg = self.config.building
        difficulty_cfg = self.config.difficulty
         
        settings = f"""[/Script/Pal.PalGameWorldSettings]
OptionSettings=(
    Difficulty={difficulty_cfg.level},
    DayTimeSpeedRate={pal_cfg.day_time_speed_rate},
    NightTimeSpeedRate={pal_cfg.night_time_speed_rate},
    ExpRate={pal_cfg.exp_rate},
    PalCaptureRate={pal_cfg.pal_capture_rate},
    PalSpawnNumRate={pal_cfg.pal_spawn_num_rate},
    PalDamageRateAttack={pal_cfg.pal_damage_rate_attack},
    PalDamageRateDefense={pal_cfg.pal_damage_rate_defense},
    PlayerDamageRateAttack={pal_cfg.player_damage_rate_attack},
    PlayerDamageRateDefense={pal_cfg.player_damage_rate_defense},
    PlayerStomachDecreaceRate={pal_cfg.player_stomach_decrease_rate},
    PlayerStaminaDecreaceRate={pal_cfg.player_stamina_decrease_rate},
    PlayerAutoHPRegeneRate={pal_cfg.player_auto_hp_regene_rate},
    PlayerAutoHpRegeneRateInSleep={pal_cfg.player_auto_hp_regene_rate_in_sleep},
    PalStomachDecreaceRate={pal_cfg.pal_stomach_decrease_rate},
    PalStaminaDecreaceRate={pal_cfg.pal_stamina_decrease_rate},
    PalAutoHPRegeneRate={pal_cfg.pal_auto_hp_regene_rate},
    PalAutoHpRegeneRateInSleep={pal_cfg.pal_auto_hp_regene_rate_in_sleep},
    BuildObjectDamageRate={building_cfg.build_object_damage_rate},
    BuildObjectDeteriorationDamageRate={building_cfg.build_object_deterioration_damage_rate},
    CollectionDropRate={building_cfg.collection_drop_rate},
    CollectionObjectHpRate={building_cfg.collection_object_hp_rate},
    CollectionObjectRespawnSpeedRate={building_cfg.collection_object_respawn_speed_rate},
    EnemyDropItemRate={building_cfg.enemy_drop_item_rate},
    DeathPenalty={difficulty_cfg.death_penalty},
    bEnablePlayerToPlayerDamage={str(gameplay_cfg.enable_player_to_player_damage).capitalize()},
    bEnableFriendlyFire={str(gameplay_cfg.enable_friendly_fire).capitalize()},
    bEnableInvaderEnemy={str(gameplay_cfg.enable_invader_enemy).capitalize()},
    bActiveUNKO={str(gameplay_cfg.active_unko).capitalize()},
    bEnableAimAssistPad={str(gameplay_cfg.enable_aim_assist_pad).capitalize()},
    bEnableAimAssistKeyboard={str(gameplay_cfg.enable_aim_assist_keyboard).capitalize()},
    DropItemMaxNum={items_cfg.drop_item_max_num},
    DropItemMaxNum_UNKO={items_cfg.drop_item_max_num_unko},
    BaseCampMaxNum={base_camp_cfg.max_num},
    BaseCampWorkerMaxNum={base_camp_cfg.worker_max_num},
    DropItemAliveMaxHours={items_cfg.drop_item_alive_max_hours},
    bAutoResetGuildNoOnlinePlayers={str(guild_cfg.auto_reset_guild_no_online_players).capitalize()},
    AutoResetGuildTimeNoOnlinePlayers={guild_cfg.auto_reset_guild_time_no_online_players},
    GuildPlayerMaxNum={guild_cfg.player_max_num},
    PalEggDefaultHatchingTime={pal_cfg.egg_default_hatching_time},
    WorkSpeedRate={pal_cfg.work_speed_rate},
    bIsMultiplay={str(gameplay_cfg.is_multiplay).capitalize()},
    bIsPvP={str(gameplay_cfg.is_pvp).capitalize()},
    bCanPickupOtherGuildDeathPenaltyDrop={str(gameplay_cfg.can_pickup_other_guild_death_penalty_drop).capitalize()},
    bEnableNonLoginPenalty={str(gameplay_cfg.enable_non_login_penalty).capitalize()},
    bEnableFastTravel={str(gameplay_cfg.enable_fast_travel).capitalize()},
    bIsStartLocationSelectByMap={str(gameplay_cfg.is_start_location_select_by_map).capitalize()},
    bExistPlayerAfterLogout={str(gameplay_cfg.exist_player_after_logout).capitalize()},
    bEnableDefenseOtherGuildPlayer={str(gameplay_cfg.enable_defense_other_guild_player).capitalize()},
    CoopPlayerMaxNum={gameplay_cfg.coop_player_max_num},
    ServerPlayerMaxNum={server_cfg.max_players},
    ServerName="{server_cfg.name}",
    ServerDescription="{server_cfg.description}",
    AdminPassword="{server_cfg.admin_password}",
    ServerPassword="{server_cfg.password}",
    PublicPort={server_cfg.port},
    PublicIP="",
    RCONEnabled={str(rcon_cfg.enabled).capitalize()},
    RCONPort={rcon_cfg.port},
    Region="{gameplay_cfg.region}",
    bUseAuth={str(gameplay_cfg.use_auth).capitalize()},
    BanListURL="{gameplay_cfg.banlist_url}",
    RESTAPIEnabled={str(api_cfg.enabled).capitalize()},
    RESTAPIPort={api_cfg.port}
)"""
        return settings
    
    def _generate_engine_content(self) -> str:
        """Generate complete Engine.ini file content using sample + performance settings with fallback"""
        try:
            # Read base content from sample file
            base_content = self._read_engine_base_content()
            
            # Generate performance settings
            performance_settings = self._generate_performance_settings()
            
            # Combine base + performance
            return self._combine_engine_content(base_content, performance_settings)
            
        except Exception as e:
            self.logger.error(f"Engine content generation failed: {e}")
            self.logger.info("Using fallback engine content generation")
            return self._generate_engine_content_fallback()
    
    def _read_engine_base_content(self) -> str:
        """
        Read base Engine.ini content from sample file with comprehensive error handling
        
        Returns:
            Base Engine.ini content as string
        """
        # Try multiple possible locations for sample file
        possible_paths = [
            self.default_engine_path,
            self.server_path / "Engine" / "Config" / "BaseEngine.ini",
            self.server_path / "Engine" / "Config" / "DefaultEngine.ini",
            Path(__file__).parent.parent.parent / "config" / "DefaultEngine.ini"
        ]
        
        for sample_path in possible_paths:
            if sample_path.exists():
                try:
                    base_content = sample_path.read_text(encoding='utf-8')
                    if base_content.strip():  # Make sure it's not empty
                        self.logger.info(f"Using Engine.ini base from: {sample_path}")
                        return base_content
                    else:
                        self.logger.warning(f"Engine.ini file is empty: {sample_path}")
                        
                except UnicodeDecodeError as e:
                    self.logger.warning(f"Unicode decode error in {sample_path}: {e}")
                    try:
                        # Try with BOM handling
                        base_content = sample_path.read_text(encoding='utf-8-sig')
                        if base_content.strip():
                            self.logger.info(f"Using Engine.ini base after BOM handling: {sample_path}")
                            return base_content
                    except Exception as bom_e:
                        self.logger.warning(f"BOM handling also failed for {sample_path}: {bom_e}")
                        
                except Exception as e:
                    self.logger.warning(f"Failed to read {sample_path}: {e}")
                    continue
        
        # Fallback to hardcoded content if no sample found
        self.logger.warning("No Engine.ini sample found, using hardcoded fallback")
        return self._get_fallback_engine_content()
    
    def _get_fallback_engine_content(self) -> str:
        """
        Fallback hardcoded content (current implementation)
        Used only when no sample file is available
        """
        return """[Core.System]
Paths=../../../Engine/Content
Paths=%GAMEDIR%Content
Paths=../../../Engine/Plugins/2D/Paper2D/Content
Paths=../../../Engine/Plugins/Animation/ControlRigSpline/Content
Paths=../../../Engine/Plugins/Animation/ControlRig/Content
Paths=../../../Engine/Plugins/Animation/IKRig/Content
Paths=../../../Engine/Plugins/Animation/MotionWarping/Content
Paths=../../../Engine/Plugins/Bridge/Content
Paths=../../../Engine/Plugins/Compositing/Composure/Content
Paths=../../../Engine/Plugins/Compositing/OpenColorIO/Content
Paths=../../../Engine/Plugins/Developer/AnimationSharing/Content
Paths=../../../Engine/Plugins/Developer/Concert/ConcertSync/ConcertSyncClient/Content
Paths=../../../Engine/Plugins/Editor/BlueprintHeaderView/Content
Paths=../../../Engine/Plugins/Editor/GeometryMode/Content
Paths=../../../Engine/Plugins/Editor/ModelingToolsEditorMode/Content
Paths=../../../Engine/Plugins/Editor/ObjectMixer/LightMixer/Content
Paths=../../../Engine/Plugins/Editor/ObjectMixer/ObjectMixer/Content
Paths=../../../Engine/Plugins/Editor/SpeedTreeImporter/Content
Paths=../../../Engine/Plugins/Enterprise/DatasmithContent/Content
Paths=../../../Engine/Plugins/Enterprise/GLTFExporter/Content
Paths=../../../Engine/Plugins/Experimental/ChaosCaching/Content
Paths=../../../Engine/Plugins/Experimental/ChaosClothEditor/Content
Paths=../../../Engine/Plugins/Experimental/ChaosNiagara/Content
Paths=../../../Engine/Plugins/Experimental/ChaosSolverPlugin/Content
Paths=../../../Engine/Plugins/Experimental/CommonUI/Content
Paths=../../../Engine/Plugins/Experimental/Dataflow/Content
Paths=../../../Engine/Plugins/Experimental/FullBodyIK/Content
Paths=../../../Engine/Plugins/Experimental/GeometryCollectionPlugin/Content
Paths=../../../Engine/Plugins/Experimental/GeometryFlow/Content
Paths=../../../Engine/Plugins/Experimental/ImpostorBaker/Content
Paths=../../../Engine/Plugins/Experimental/Landmass/Content
Paths=../../../Engine/Plugins/Experimental/MeshLODToolset/Content
Paths=../../../Engine/Plugins/Experimental/PythonScriptPlugin/Content
Paths=../../../Engine/Plugins/Experimental/StaticMeshEditorModeling/Content
Paths=../../../Engine/Plugins/Experimental/UVEditor/Content
Paths=../../../Engine/Plugins/Experimental/Volumetrics/Content
Paths=../../../Engine/Plugins/Experimental/Water/Content
Paths=../../../Engine/Plugins/FX/Niagara/Content
Paths=../../../Engine/Plugins/JsonBlueprintUtilities/Content
Paths=../../../Engine/Plugins/Media/MediaCompositing/Content
Paths=../../../Engine/Plugins/Media/MediaPlate/Content
Paths=../../../Engine/Plugins/MovieScene/SequencerScripting/Content
Paths=../../../Engine/Plugins/PivotTool/Content
Paths=../../../Engine/Plugins/PlacementTools/Content
Paths=../../../Engine/Plugins/Runtime/AudioSynesthesia/Content
Paths=../../../Engine/Plugins/Runtime/AudioWidgets/Content
Paths=../../../Engine/Plugins/Runtime/GeometryProcessing/Content
Paths=../../../Engine/Plugins/Runtime/Metasound/Content
Paths=../../../Engine/Plugins/Runtime/ResonanceAudio/Content
Paths=../../../Engine/Plugins/Runtime/SunPosition/Content
Paths=../../../Engine/Plugins/Runtime/Synthesis/Content
Paths=../../../Engine/Plugins/Runtime/WaveTable/Content
Paths=../../../Engine/Plugins/Runtime/WebBrowserWidget/Content
Paths=../../../Engine/Plugins/SkyCreatorPlugin/Content
Paths=../../../Engine/Plugins/VirtualProduction/CameraCalibrationCore/Content
Paths=../../../Engine/Plugins/VirtualProduction/LiveLinkCamera/Content
Paths=../../../Engine/Plugins/VirtualProduction/Takes/Content
Paths=../../../Engine/Plugins/Web/HttpBlueprint/Content
Paths=../../../Pal/Plugins/DLSS/Content
Paths=../../../Pal/Plugins/EffectsChecker/Content
Paths=../../../Pal/Plugins/HoudiniEngine/Content
Paths=../../../Pal/Plugins/PPSkyCreatorPlugin/Content
Paths=../../../Pal/Plugins/PocketpairUser/Content
Paths=../../../Pal/Plugins/SpreadSheetToCsv/Content
Paths=../../../Pal/Plugins/WwiseNiagara/Content
Paths=../../../Pal/Plugins/Wwise/Content"""
    
    def _combine_engine_content(self, base_content: str, performance_settings: str) -> str:
        """
        Combine base Engine.ini content with performance settings
        
        Args:
            base_content: Base Engine.ini content from sample
            performance_settings: Performance optimization settings
            
        Returns:
            Complete Engine.ini content
        """
        # Ensure base_content ends with newline
        if not base_content.endswith('\n'):
            base_content += '\n'
        
        # Add separator comment
        separator = "\n# Performance optimization settings (auto-generated)\n"
        
        # Combine all content
        return base_content + separator + performance_settings
    
    def _generate_performance_settings(self) -> str:
        """Generate performance settings section using config values"""
        engine_cfg = self.config.engine
        
        return f"""
[/script/onlinesubsystemutils.ipnetdriver]
LanServerMaxTickRate={engine_cfg.lan_server_max_tick_rate}
NetServerMaxTickRate={engine_cfg.net_server_max_tick_rate}

[/script/engine.player]
ConfiguredInternetSpeed={engine_cfg.configured_internet_speed}
ConfiguredLanSpeed={engine_cfg.configured_lan_speed}

[/script/socketsubsystemepic.epicnetdriver]
MaxClientRate={engine_cfg.max_client_rate}
MaxInternetClientRate={engine_cfg.max_internet_client_rate}

[/script/engine.engine]
bSmoothFrameRate={str(engine_cfg.smooth_frame_rate).capitalize()}
bUseFixedFrameRate={str(engine_cfg.use_fixed_frame_rate).capitalize()}
SmoothedFrameRateRange=(LowerBound=(Type=Inclusive,Value={engine_cfg.frame_rate_lower_bound}),UpperBound=(Type=Exclusive,Value={engine_cfg.frame_rate_upper_bound}))
MinDesiredFrameRate={engine_cfg.min_desired_frame_rate}
FixedFrameRate={engine_cfg.fixed_frame_rate}
NetClientTicksPerSecond={engine_cfg.net_client_ticks_per_second}"""
    
    def _generate_engine_content_fallback(self) -> str:
        """
        Fallback engine content generation (legacy method)
        Used when sample file parsing fails completely
        """
        base_content = self._get_fallback_engine_content()
        performance_settings = self._generate_performance_settings()
        return self._combine_engine_content(base_content, performance_settings)
    
    def get_config_summary(self) -> Dict[str, Any]:
        """
        Get configuration summary for debugging and monitoring
        
        Returns:
            Dictionary with configuration summary
        """
        try:
            defaults = self._get_default_settings()
            user_settings = asdict(self.config.palworld_settings)
            
            overrides = {}
            new_settings = {}
            
            for key, value in user_settings.items():
                formatted_value = self._format_ini_value(value)
                if key in defaults:
                    if defaults[key] != formatted_value:
                        overrides[key] = {
                            'default': defaults[key],
                            'override': formatted_value
                        }
                else:
                    new_settings[key] = formatted_value
            
            return {
                'parsing_status': 'success' if defaults else 'failed',
                'total_defaults_found': len(defaults),
                'total_user_settings': len(user_settings),
                'total_overrides': len(overrides),
                'total_new_settings': len(new_settings),
                'overrides': overrides,
                'new_settings': new_settings,
                'sample_file_locations': {
                    'settings_file': str(self.default_settings_path),
                    'engine_file': str(self.default_engine_path),
                    'settings_exists': self.default_settings_path.exists(),
                    'engine_exists': self.default_engine_path.exists()
                },
                'fallback_used': len(defaults) == 0
            }
            
        except Exception as e:
            return {
                'parsing_status': 'error',
                'error': str(e),
                'fallback_used': True
            }
