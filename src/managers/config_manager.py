#!/usr/bin/env python3
"""
Configuration file management for Palworld server
Handles PalWorldSettings.ini and Engine.ini generation
"""

from pathlib import Path

from ..config_loader import PalworldConfig
from ..logging_setup import log_server_event


class ConfigManager:
    """Server configuration file management"""
    
    def __init__(self, config: PalworldConfig, logger):
        self.config = config
        self.logger = logger
        self.server_path = config.paths.server_dir
        self.config_dir = self.server_path / "Pal" / "Saved" / "Config" / "LinuxServer"
    
    def generate_server_settings(self) -> bool:
        """Generate Palworld server settings file"""
        try:
            settings_file = self.config_dir / "PalWorldSettings.ini"
            
            # Ensure directory exists
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate settings content
            settings_content = self._generate_settings_content()
            
            settings_file.write_text(settings_content, encoding='utf-8')
            
            log_server_event(self.logger, "config_generate", 
                           "Server settings file generated", 
                           settings_file=str(settings_file))
            return True
            
        except Exception as e:
            log_server_event(self.logger, "config_generate_fail", 
                           f"Failed to generate settings file: {e}")
            return False
    
    def generate_engine_settings(self) -> bool:
        """Generate Palworld engine settings file"""
        try:
            engine_file = self.config_dir / "Engine.ini"
            
            # Ensure directory exists
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate engine content
            engine_content = self._generate_engine_content()
            
            engine_file.write_text(engine_content, encoding='utf-8')
            
            log_server_event(self.logger, "config_generate", 
                           "Engine settings file generated", 
                           engine_file=str(engine_file))
            return True
            
        except Exception as e:
            log_server_event(self.logger, "config_generate_fail", 
                           f"Failed to generate engine settings file: {e}")
            return False
    
    def _generate_settings_content(self) -> str:
        """Generate complete settings file content using all config values"""
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
    PlayerStomachDecreaseRate={pal_cfg.player_stomach_decrease_rate},
    PlayerStaminaDecreaseRate={pal_cfg.player_stamina_decrease_rate},
    PlayerAutoHPRegeneRate={pal_cfg.player_auto_hp_regene_rate},
    PlayerAutoHpRegeneRateInSleep={pal_cfg.player_auto_hp_regene_rate_in_sleep},
    PalStomachDecreaseRate={pal_cfg.pal_stomach_decrease_rate},
    PalStaminaDecreaseRate={pal_cfg.pal_stamina_decrease_rate},
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
        """Generate complete Engine.ini file content using config values"""
        engine_cfg = self.config.engine
        
        # Base Engine.ini content (original paths)
        base_paths = """[Core.System]
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

        # Performance optimization settings using config values
        performance_settings = f"""

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

        return base_paths + performance_settings
