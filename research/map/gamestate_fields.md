# The fighters' module fields: carried, recomputed, constant

Written by `research/tools/live.py md` from `live_state.json` (28 whole-fight runs: cpu_bowser_greninja, cpu_charizard_ivysaur, cpu_dedede_zss, cpu_falcon_metaknight, cpu_hero_robin, cpu_ice_olimar_items, cpu_incin_mewtwo, cpu_lucina_wario, cpu_mac_joker, cpu_marth_megaman, cpu_richter_shulk, cpu_roy_sheik, cpu_steve_inkling, four_cpu_items, four_cpu_kalos, items_cpu_four, items_cpu_samus_fox, lylat_sephiroth_sora, smashville_corrin_mm, stadium2_falco_ike, yoshistory_wiifit_krool).
Method: at every rollback safe point of a fight (2,000 a run) each byte's first access starts again (runtime: `SSBU_LIVE`). A field is

- **carried**: read before written after some safe point, and written during the fight: state a load must put back;
- **recomputed**: written before read after every safe point of every run where it was touched: a load need not put it back
  (tested in the ring for the fighters of the runs: see research/RESEARCH.md, 2026-11-13);
- **constant**: read, never written in the fight (pointers, tables, sizes): a load never changes it;
- not touched: no access in any run.

Field names are the code reading's (`research/map/code_reading/modules/`); "verified" = the game confirmed the field yesterday
(getter probe, write watch or the series' check). Offsets are in the module object; the module is at the given offset of the module accessor.

Totals: carried 428, constant 439, not touched 166, recomputed 135; verified: carried 276, constant 34, not touched 13, recomputed 97.

## PostureModule (accessor +0x38, 208 bytes)

Bytes: carried 70, recomputed 44, constant 40, handed over 0.

**carried** (13): pos* (+0x30, 16), pos_x (+0x30, 4), pos_y (+0x34, 4), pos_z (+0x38, 4), prev_pos* (+0x40, 16), pos_delta (saved pos - prev_pos)* (+0x60, 16), pos_changed (pos differed from prev_pos at slot 0x160) (+0x70, 1), scale_status* (+0xa4, 4), scale_sent_to_links (last base_scale pushed by set_scale(...,true))* (+0xa8, 4), lr* (+0xac, 4), rot_y_lr* (+0xb0, 4), link_scale* (+0xb8, 4), ignore_link_scale (scale uses owner_scale instead of link_scale)* (+0xc8, 1)

**recomputed** (4): saved_pos (restore point for interpolation)* (+0x50, 16), start_pos (position given at reset)* (+0x80, 16), link_scale_sent_to_links* (+0xbc, 4), sync_constraint_joint* (+0xc0, 8)

**constant** (4): rot_count (number of rotation entries) (+0x90, 4), rot_entries (array of 0x60-byte rotation entries) (+0x98, 8), base_scale* (+0xa0, 4), owner_scale* (+0xb4, 4)

**not touched** (2): flags (bitmask) (+0x18, 4), flag_suspend_counter (+0x1c, 4)

## StatusModule (accessor +0x40, 392 bytes)

Bytes: carried 95, recomputed 118, constant 62, handed over 0.

**carried** (13): status_kind* (+0x98, 4), status_kind_que_from_script* (+0xa4, 4), is_changing* (+0xf4, 1), situation_kind* (+0xdc, 4), prev_situation_kind* (+0xe0, 4), succeeds_bits (+0xbc, 4), current_status_handler (+0xe8, 8), keep_situation_air (+0xf8, 1), situation_locked (+0xf7, 1), in_lua_status_init (+0xf0, 1), in_lua_status_end (+0xf1, 1), request_done_this_frame (+0xf2, 1), fighter_status_data (+0x100, 64)

**recomputed** (14): status_kind_next* (+0x9c, 4), status_kind_interrupt* (+0xa0, 4), kinetic_type (+0xb8, 4), ground_correct_kind (+0xd0, 4), ground_cliff_check_kind (+0xd4, 4), keep_flag_kind (+0xc4, 4), keep_int_kind (+0xc8, 4), keep_float_kind (+0xcc, 4), status_data (+0xa8, 8), prev_status_data (+0xb0, 8), que_from_script_clear_buffer (+0xf6, 1), status_changed_flag (+0xf3, 1), in_status_handler_end (+0xf9, 1), fighter_prev_status_data (+0x140, 64)

**constant** (9): status_history_ring (+0x80, 8), succeeds_bits_extra (+0xc0, 4), lua_status_func_mask (+0xd8, 4), status_handler_table_count (+0x88, 8), status_handler_table (+0x90, 8), status_funcs_disabled (+0xf5, 1), boma (+0x8, 8), request_queue_count (+0x20, 8), fighter_extra_ptr (+0x180, 8)

**not touched** (6): request_queue_vptr (+0x10, 8), request_queue_capacity (+0x18, 8), request_queue_read_index (+0x28, 8), request_queue_write_index (+0x30, 8), request_queue_data (+0x38, 8), request_queue_entries (+0x40, 64)

## ControlModule (accessor +0x48, 2800 bytes)

Bytes: carried 1010, recomputed 576, constant 451, handed over 0.

(no field names: carried byte ranges +0x30..+0x40, +0x60..+0x70, +0x90..+0x94, +0x9c..+0xa0, +0xa8..+0xac, +0xb0..+0xb2, +0xb3..+0xb4, +0xb5..+0xb8, +0xb9..+0xba, +0xbb..+0xbc, +0xbd..+0xbe, +0xbf..+0xc0)

## WorkModule (accessor +0x50, 152 bytes)

Bytes: carried 17, recomputed 8, constant 76, handed over 0.

**carried** (3): fighter_entry_work (+0x50, 8), unknown_ptr_58 (+0x58, 8), force_param_reset (+0x88, 1)

**recomputed** (1): tail_8c (+0x8c, 12)

**constant** (11): vptr (+0x0, 8), owner (+0x8, 8), work_tables (+0x18, 8), transition_term_count (+0x20, 4), transition_term_bytes (+0x28, 8), transition_group_table (+0x30, 8), param_accessor (+0x38, 8), param_kind (+0x40, 4), entry_id (+0x44, 4), param_override_list (+0x70, 8), param_override_count (+0x78, 8)

**not touched** (5): work_tables_header (+0x10, 8), unknown_48 (+0x48, 8), override_array (+0x60, 8), override_array_count (+0x68, 8), unknown_scale_80 (+0x80, 4)

## GroundModule (accessor +0x58, 368 bytes)

Bytes: carried 95, recomputed 49, constant 110, handed over 0.

(no field names: carried byte ranges +0x30..+0x38, +0x40..+0x48, +0x60..+0x80, +0xbc..+0xc8, +0xcc..+0xd0, +0xf0..+0xf4, +0x110..+0x114, +0x116..+0x118, +0x120..+0x121, +0x130..+0x140, +0x168..+0x16c)

## CameraModule (accessor +0x60, 88 bytes)

Bytes: carried 6, recomputed 0, constant 56, handed over 0.

(no field names: carried byte ranges +0x10..+0x15, +0x19..+0x1a)

## KineticModule (accessor +0x68, 3440 bytes)

Bytes: carried 461, recomputed 72, constant 261, handed over 0.

(no field names: carried byte ranges +0x1b8..+0x1bc, +0x1bd..+0x1be, +0x5f0..+0x600, +0x610..+0x612, +0x640..+0x660, +0x661..+0x662, +0x664..+0x674, +0x678..+0x6a1, +0x6c0..+0x6d0, +0x6e0..+0x6e2, +0x6e4..+0x70d, +0x720..+0x726)

## ColorBlendModule (accessor +0x70, 1568 bytes)

Bytes: carried 395, recomputed 190, constant 96, handed over 0.

**carried** (53): main_color_enabled* (+0xb0, 1), main_color_frames* (+0x200, 4), flash0_color (+0x410, 16), flash0_start_color (+0x420, 16), flash0_target_color (+0x430, 16), flash0_color_mul (+0x440, 16), flash0_direction* (+0x450, 16), flash0_shadow_bloom* (+0x460, 4), flash0_frame_counter* (+0x464, 4), flash0_frames* (+0x468, 4), flash0_f5c (+0x46c, 4), flash0_priority* (+0x470, 4), flash0_active* (+0x474, 1), flash0_transition* (+0x475, 1), flash0_flag* (+0x476, 1), flash1_color (+0x480, 16), flash1_start_color (+0x490, 16), flash1_target_color (+0x4a0, 16), flash1_color_mul (+0x4b0, 16), flash1_direction* (+0x4c0, 16), flash1_shadow_bloom* (+0x4d0, 4), flash1_frame_counter (+0x4d4, 4), flash1_frames (+0x4d8, 4), flash1_f5c (+0x4dc, 4), flash1_priority* (+0x4e0, 4), flash1_active (+0x4e4, 1), flash1_transition (+0x4e5, 1), flash1_flag* (+0x4e6, 1), burn0_color (+0x4f0, 16), burn0_start_color (+0x500, 16), burn0_target_color (+0x510, 16), burn0_color_mul (+0x520, 16), burn0_frame_counter* (+0x544, 4), burn0_frames* (+0x548, 4), burn0_f5c (+0x54c, 4), burn0_priority* (+0x550, 4), burn0_active (+0x554, 1), burn0_transition* (+0x555, 1), burn1_color (+0x560, 16), burn1_start_color (+0x570, 16), burn1_target_color (+0x580, 16), burn1_color_mul (+0x590, 16), burn1_frame_counter (+0x5b4, 4), burn1_frames* (+0x5b8, 4), burn1_f5c (+0x5bc, 4), burn1_priority* (+0x5c0, 4), burn1_active (+0x5c4, 1), burn1_transition (+0x5c5, 1), status* (+0x600, 1), flag_602 (+0x602, 1), reset_channel1_request* (+0x603, 1), disable_camera_depth_influence* (+0x605, 1), last_attack_direction* (+0x610, 16)

**recomputed** (8): main_color_current (+0x10, 160), burn0_direction* (+0x530, 16), burn0_f50* (+0x540, 4), burn0_flag* (+0x556, 1), burn1_direction* (+0x5a0, 16), burn1_f50* (+0x5b0, 4), burn1_flag* (+0x5c6, 1), model_module (+0x5d8, 8)

**constant** (15): vptr (+0x0, 8), owner_boma (+0x8, 8), main_color_link_id (+0xb4, 4), main_color_frame_counter (+0x204, 4), main_color_2_current (+0x210, 160), main_color_2_enabled (+0x2b0, 1), main_color_2_link_id (+0x2b4, 4), main_color_2_frames (+0x400, 4), main_color_2_frame_counter (+0x404, 4), blend_priority (+0x5d0, 4), u5d4 (+0x5d4, 4), owned_target (+0x5e0, 8), flag_601 (+0x601, 1), enable_flash (+0x604, 1), u608 (+0x608, 4)

**not touched** (8): main_color_target (+0xc0, 160), main_color_start (+0x160, 160), main_color_flag (+0x208, 1), main_color_2_target (+0x2c0, 160), main_color_2_start (+0x360, 160), main_color_2_flag (+0x408, 1), target_node (+0x5e8, 8), u5f0 (+0x5f0, 4)

## ModelModule (accessor +0x78, 464 bytes)

Bytes: carried 62, recomputed 4, constant 156, handed over 0.

**carried** (11): scale_aux (1.0)* (+0x38, 4), joint_update_state (0/1/2)* (+0x3c, 4), model_index_or_mode (-1)* (+0x94, 4), color[MODEL_COLOR_TYPE] {rgb f32x3, a f32, pad 16, f32 x2 (1.0), u64} (+0xe0, 96), update_flag_140* (+0x140, 1), joint_cache_valid* (+0x145, 1), flag_146* (+0x146, 1), flag_147* (+0x147, 1), flag_148 (+0x148, 1), gold_eye_flags (bit0 gold eye, bits1/2 other eye materials)* (+0x150, 8), flag_159* (+0x159, 1)

**recomputed** (1): joint_offset_scale* (+0x90, 4)

**constant** (16): vptr (+0x0, 8), owner_boma (+0x8, 8), model (render model instance) (+0x10, 8), skeleton_or_joint_data (+0x18, 8), scale* (+0x30, 4), scale_z* (+0x34, 4), rotation_order* (+0x40, 4), external_matrix_source (+0x48, 8), fade_a {start, current, step, target} (+0x70, 16), fade_b {start, frame, step, value} (+0x80, 16), virtual_joint_table (buckets +0x98, bucket_count +0xA0) keyed by Hash40 (+0x98, 16), owned_object_c8 (+0xc8, 8), fade_a_active (+0x141, 1), fade_b_active (+0x142, 1), external_matrix_enabled (+0x144, 1), eye_material_locked (+0x158, 1)

**not touched** (10): joint_matrix_buffers (swapped) (+0x20, 16), aux_pointers* (+0x50, 16), aux_count (+0x60, 4), blend_values_a (+0x64, 12), unknown_one (1.0) (+0xb8, 4), scale_z_changed (+0x143, 1), owned_buffers_168 (+0x168, 16), owned_178 (+0x178, 8), owned_1b0 (+0x1b0, 8), fighter_flag_1c0 (+0x1c0, 1)

## PhysicsModule (accessor +0x80, 208 bytes)

Bytes: carried 45, recomputed 10, constant 79, handed over 0.

**carried** (8): scale (1.0)* (+0x80, 4), swing_rate* (+0x94, 4), charge_value* (+0x98, 4), base_vector (init from a global constant)* (+0xa0, 16), swing_wind* (+0xc0, 1), swing_enabled (init 1)* (+0xc4, 1), charging* (+0xc7, 1), ik_ready* (+0xca, 1)

**recomputed** (2): ring_buffer.count* (+0x38, 8), ik_dirty* (+0xcb, 1)

**constant** (16): vptr (+0x0, 8), owner (BattleObjectModuleAccessor) (+0x8, 8), ik_count (+0x10, 4), ik_entries (array, 0x40 bytes per entry) (+0x18, 8), physics_controller (from MotionModule slot 0x610) (+0x20, 8), ring_buffer.capacity (=32) (+0x30, 8), ring_buffer.data (32 entries of 0x30 bytes) (+0x40, 8), swing_state (0 = no swing) (+0x90, 4), record_count (setup arg3 first word) (+0xb0, 8), record_array (0x14 bytes per record) (+0xb8, 8), swing_wind_locked (+0xc1, 1), swing_enabled_default (init 1) (+0xc5, 1), swing_only_anim_lock (+0xc6, 1), has_controller_b (+0xcc, 1), has_joint_params (+0xcd, 1), flag_ce (unnamed) (+0xce, 1)

**not touched** (5): ring_buffer.vptr (embedded container, vtable 0x7104f71c68) (+0x28, 8), param_block[0] (setup descriptor, +0x48..+0x7c) (+0x48, 8), param_block.count_or_kind (+0x50) (+0x50, 4), has_swing_data (+0xc8, 1), has_controller_a (+0xc9, 1)

## MotionModule (accessor +0x88, 784 bytes)

Bytes: carried 267, recomputed 56, constant 271, handed over 0.

**carried** (57): joint_srt_count* (+0x58, 4), motion_kind* (+0x68, 8), frame* (+0x70, 4), prev_frame* (+0x74, 4), main_motion.unk_0x18* (+0x78, 4), rate* (+0x7c, 4), frame_secondary* (+0x80, 4), main_motion.rate_scale* (+0x88, 4), end_frame_f* (+0x8c, 4), main_motion.anim_index* (+0x90, 4), main_motion.loop* (+0x94, 1), main_motion.flag_0x35* (+0x95, 1), main_motion.changed* (+0x97, 1), main_motion.shift_material* (+0x98, 1), main_motion.reverse (+0x9a, 1), motion_kind_2nd* (+0xa8, 8), frame_2nd* (+0xb0, 4), rate_2nd* (+0xbc, 4), frame_2nd_secondary* (+0xc0, 4), end_frame_2nd_f* (+0xcc, 4), motion_2nd.loop* (+0xd4, 1), motion_2nd.reverse* (+0xda, 1), trans_move_speed_raw* (+0x100, 16), weight* (+0x1e0, 4), prev_weight* (+0x1e4, 4), weight_rate* (+0x1ec, 4), partial_count* (+0x200, 4), whole_rate* (+0x204, 4), unk_0x20c* (+0x20c, 4), dynamic_skeleton_state* (+0x210, 4), recalc_ik_state* (+0x214, 4), stop_interpolation_frames* (+0x21c, 4), stop_interpolation_flag* (+0x220, 1), frame_material* (+0x224, 4), motion_flags* (+0x234, 2), animcmd_done* (+0x236, 1), is_changing* (+0x238, 1), no_animation* (+0x239, 1), is_flip* (+0x23a, 1), pending_flip* (+0x23c, 1), flip_deferred* (+0x23d, 1), link_flip_target_joint (+0x23e, 1), trans_move_speed_no_scale* (+0x242, 1), force_progress_2nd_weight* (+0x243, 1), no_comp* (+0x244, 1), unk_0x253* (+0x253, 1), keep_pose_change_motion* (+0x25b, 1), remove_partial_after_intp (+0x25c, 1), remove_2nd_on_change_motion (+0x25d, 1), part_animcmd_fix (+0x25e, 1), fighter.unk_vec_0x290 (+0x290, 32), fighter.hash_0x2b8 (+0x2b8, 8), fighter.unk_0x2c0 (+0x2c0, 4), fighter.unk_0x2c4 (+0x2c4, 4), fighter.unk_0x2c8 (+0x2c8, 8), fighter.unk_0x2f0 (+0x2f0, 2), fighter.hash_0x300 (+0x300, 8)

**recomputed** (7): prev_frame_secondary* (+0x84, 4), main_motion.flag_0x39* (+0x99, 1), prev_frame_2nd* (+0xb4, 4), motion_2nd.rate_scale* (+0xc8, 4), trans_move_speed_2nd_raw (+0x130, 16), kind_offset* (+0x218, 4), calc_joint_busy* (+0x248, 1)

**constant** (30): vptr (+0x0, 8), owner_boma (+0x8, 8), model_anim_controller (+0x10, 8), link_list_a (+0x18, 8), link_list_b (+0x20, 8), link_list_a_count (+0x28, 4), link_list_b_count (+0x2c, 4), owned_buffer (+0x38, 8), trans_joint_id (+0x40, 8), joint_srt_array (+0x50, 8), main_motion.vptr (+0x60, 8), main_motion.flag_0x36 (+0x96, 1), motion_2nd.vptr (+0xa0, 8), motion_2nd.flag_0x36 (+0xd6, 1), partial_motions (+0xe8, 8), motion_resource (+0x148, 8), motion_resource_refcount (+0x150, 8), motion_kind_remap_fn (+0x190, 8), skip_rate (+0x1f0, 4), trans_joint_scale* (+0x1fc, 4), unk_rate_0x208 (+0x208, 4), end_frame_material (+0x228, 4), rate_material (+0x22c, 4), shift_material_animation (+0x245, 1), unk_0x24a (+0x24a, 1), link_no (+0x260, 4), fighter.unk_0x264 (+0x264, 4), fighter.unk_0x270 (+0x270, 4), fighter.unk_0x2d4 (+0x2d4, 4), fighter.unk_0x2d8 (+0x2d8, 8)

**not touched** (10): partial_array_begin (+0xe0, 8), shared_ctrl_0x160 (+0x160, 8), motion_kind_remap_fn_storage (+0x170, 32), shared_obj_0x1a0 (+0x1a0, 8), shared_ctrl_0x1a8 (+0x1a8, 8), weight_unk_0x1e8 (+0x1e8, 4), resource_not_flipped* (+0x23b, 1), skip_rate_flag (+0x249, 1), fighter.joint_top (+0x278, 8), fighter.joint_handr (+0x280, 8)

## StopModule (accessor +0x90, 80 bytes)

Bytes: carried 50, recomputed 1, constant 17, handed over 0.

**carried** (20): hit_stop_real_frame* (+0x10, 4), hit_stop_frame_fix (+0x14, 4), hit_stop_frame_fix_life* (+0x18, 4), other_stop_frame[STOP_OTHER_KIND_NORMAL] (+0x1c, 4), other_stop_pending_frame[NORMAL] (+0x20, 4), other_stop_active[NORMAL] (+0x24, 1), other_stop_frame[STOP_OTHER_KIND_FINISH_CAMERA] (+0x28, 4), other_stop_pending_frame[FINISH_CAMERA] (+0x2c, 4), other_stop_active[FINISH_CAMERA]* (+0x30, 1), item_stop_frame* (+0x34, 4), item_stop_pending_frame (+0x38, 4), is_stop* (+0x3c, 1), is_hit* (+0x3d, 1), is_damage* (+0x3e, 1), is_item* (+0x3f, 1), link_stop* (+0x40, 1), link_stop_arg2* (+0x41, 1), is_special_stop* (+0x42, 1), in_link_notify (reentrancy guard)* (+0x43, 1), fighter_link_release_timer* (+0x48, 4)

**recomputed** (1): is_other* (+0x44, 1)

**constant** (3): vptr (+0x0, 8), owner_boma (+0x8, 8), fighter_item_stop_facial_set (+0x4c, 1)

## ArticleModule (accessor +0x98, 608 bytes)

Bytes: carried 120, recomputed 8, constant 48, handed over 0.

**carried** (5): active_list.count* (+0x20, 8), active_list.head* (+0x28, 8), active_list.tail* (+0x30, 8), active_list.storage (+0x40, 512), generate_item_pos (+0x250, 16)

**constant** (6): vptr (+0x0, 8), owner_boma (+0x8, 8), active_list.capacity (+0x18, 8), active_list.data (+0x38, 8), article_pool (+0x240, 8), external_article_holder (+0x248, 8)

**not touched** (1): active_list.vptr (+0x10, 8)

## AttackModule (accessor +0xa0, 608 bytes)

Bytes: carried 138, recomputed 35, constant 199, handed over 0.

**carried** (43): group_used_num* (+0x30, 4), owner_object_id (+0x38, 4), is_hit_abs* (+0x48, 1), no_team* (+0x49, 1), overlap_hit (+0x4b, 1), active_attack_count* (+0x80, 4), active_part_num* (+0x84, 4), pos_x* (+0x90, 4), pos_y* (+0x94, 4), pos_pad* (+0x98, 8), safe_pos_enabled* (+0xc0, 1), safe_pos_pending* (+0xc1, 1), power_mul_status* (+0xe0, 4), power_add_status* (+0xe4, 4), power_speed_status* (+0xe8, 4), power_mul_5th* (+0x100, 4), reaction_mul_3rd (+0x19c, 4), damage_reaction_mul* (+0x1a4, 4), lr* (+0x1a8, 4), is_critical_attack* (+0x1b8, 1), critical_attack_damage_mul* (+0x1bc, 4), critical_attack_reaction_mul* (+0x1c0, 4), shield_stiff_mul* (+0x1c4, 4), inflict* (+0x1d4, 4), inflict_status* (+0x1d8, 4), indirect_object_id* (+0x1dc, 4), power_up* (+0x1e0, 4), power_up_attr* (+0x1ec, 4), attacker_attribute* (+0x1f0, 1), attack_reference_joint* (+0x1f8, 8), attack_direction_axis_x* (+0x200, 4), attack_direction_axis_y* (+0x204, 4), attack_direction_axis_z* (+0x208, 4), attack_power_mul_pattern* (+0x20c, 4), attack_power_mul_scale* (+0x210, 4), damage_shake_scale* (+0x228, 4), sleep (+0x238, 1), flag_0x239* (+0x239, 1), speed_auto* (+0x23a, 1), indirect_flag* (+0x241, 1), power_up_reaction* (+0x243, 1), flag_0x244* (+0x244, 1), no_world_scale (+0x249, 1)

**recomputed** (9): speed_x* (+0xa0, 4), speed_yzw (+0xa4, 12), power_speed_limit* (+0xec, 4), attack_scale_effective* (+0x1ac, 4), start_kind_value* (+0x1d0, 4), latest_no* (+0x22c, 4), scale_follow* (+0x23c, 1), latest_absolute* (+0x240, 1), attack_occur* (+0x245, 1)

**constant** (41): vtable (+0x0, 8), owner_boma (+0x8, 8), group_capacity (+0x20, 8), group_array (+0x28, 8), unknown_0x34 (+0x34, 4), owner_category (+0x3c, 1), team_info_a (+0x40, 8), tip_enabled (+0x4a, 1), group_records (+0x58, 8), part_size* (+0x60, 8), attack_records (+0x68, 8), absolute_num (+0x70, 8), absolute_records (+0x78, 8), base_offset (+0xb0, 16), team_info (+0xc8, 8), lerp_num (+0xd0, 8), power_mul* (+0xf0, 4), power_mul_2nd* (+0xf4, 4), power_mul_3rd* (+0xf8, 4), power_mul_4th* (+0xfc, 4), customize_attack_ratio* (+0x108, 4), power_mul_6th (+0x104, 4), power_mul_by_kind_dirty (+0x174, 1), map_flag (+0x190, 1), reaction_mul (+0x194, 4), reaction_mul_2nd* (+0x198, 4), reaction_mul_4th (+0x1a0, 4), attack_scale (+0x1b0, 4), attack_scale_2nd (+0x1b4, 4), unknown_mul_0x1C8 (+0x1c8, 4), ignore_just_shield (+0x1cc, 1), power_clamp_max (+0x1e8, 4), callback_0x218 (+0x218, 8), reaction_mul_callback (+0x220, 8), setup_kind (+0x234, 4), start_flag (+0x23d, 1), disable_power_add_status_zero (+0x23e, 1), lr_check_default* (+0x23f, 1), reflect_attack (+0x242, 1), constraint_pos* (+0x246, 1), no_dead_damage_fly_effect* (+0x248, 1)

**not touched** (12): group_container (+0x10, 16), group_num (+0x50, 8), lerp_records (+0xd8, 8), power_mul_by_kind (+0x10c, 104), map_begin (+0x178, 8), map_root (+0x180, 8), map_size (+0x188, 8), power_clamp_min (+0x1e4, 4), damage_effect_mul_scale* (+0x230, 4), restrict (+0x23b, 1), flag_0x247 (+0x247, 1), camera_quake_forced_callback (+0x250, 8)

## DamageModule (accessor +0xa8, 976 bytes)

Bytes: carried 154, recomputed 81, constant 223, handed over 0.

**carried** (15): no_reaction_forced_state* (+0x20, 4), no_reaction_mode* (+0x24, 4), no_reaction_filter* (+0x30, 4), no_reaction_no_effect* (+0x46, 1), attacker_info (+0x48, 40), damage_log (+0x80, 280), damage_log.reaction_frame* (+0xc8, 4), damage_log.collision_attr* (+0xd0, 8), damage_mul* (+0x360, 4), damage_mul_2nd (+0x364, 4), reaction_mul (+0x36c, 4), reaction_mul_2nd* (+0x370, 4), reaction_mul_4th (+0x378, 4), damage_lock* (+0x384, 1), damage_lock_2nd* (+0x385, 1)

**recomputed** (7): no_reaction_reaction_threshold (+0x28, 4), no_reaction_damage_power_threshold (+0x2c, 4), object_id_37c* (+0x37c, 4), flag_388* (+0x388, 1), critical_hit* (+0x38a, 1), flag_38b* (+0x38b, 1), fighter_3c0* (+0x3c0, 4)

**constant** (19): vptr (+0x0, 8), owner_boma (+0x8, 8), damage_record_count (+0x10, 8), damage_records (+0x18, 8), no_reaction_mode_2 (+0x34, 4), no_reaction_reaction_threshold_2 (+0x38, 4), no_reaction_filter_2 (+0x40, 4), no_reaction_flag (+0x44, 1), no_reaction_mode_perfect* (+0x45, 1), setup_arg_ptr (+0x70, 8), damage_helper (+0x78, 8), force_damage_mul (+0x368, 4), reaction_mul_3rd (+0x374, 4), sleep (+0x386, 1), ignore_capture_cut_no (+0x387, 1), damage_info_log_active (+0x389, 1), flag_38c (+0x38c, 1), fighter_flag_38d (+0x38d, 1), fighter_390 (+0x390, 16)

**not touched** (6): no_reaction_damage_power_threshold_2 (+0x3c, 4), last_damage_info.damage (+0x1a0, 4), info_log_count (+0x1ac, 4), info_log_value (+0x1b0, 4), last_damage_info.collision_attr (+0x258, 8), fighter_vectors_3a0 (+0x3a0, 32)

## HitModule (accessor +0xb0, 200 bytes)

Bytes: carried 22, recomputed 1, constant 100, handed over 0.

**carried** (7): owner_object_id (+0x38, 4), no_team* (+0x49, 1), defense_mul_status (+0x88, 4), hit_stop_mul* (+0x8c, 4), hit_stop_mul_threshold* (+0x98, 4), cached_total_status_0* (+0xa0, 4), hit_stop_mul_target* (+0xa9, 1)

**recomputed** (1): unknown_a6_flag* (+0xa6, 1)

**constant** (18): vptr (+0x0, 8), owner_boma (+0x8, 8), hit_group_count (+0x20, 8), hit_groups (+0x28, 8), hit_group_count_u32 (+0x30, 4), unknown_34 (+0x34, 4), object_category (+0x3c, 1), team_no (+0x40, 8), unknown_4a (+0x4a, 1), hit_entry_count (+0x58, 8), hit_entries (+0x60, 8), hit_parts (+0x70, 8), defense_mul_param_hash (+0x80, 8), unknown_90 (+0x90, 8), reaction_frame (+0xa4, 2), sleep (+0xa7, 1), setup_param_8 (+0xa8, 1), unknown_b8 (+0xb8, 4)

**not touched** (7): embedded_collision_set_start (+0x10, 8), setup_param_0 (+0x50, 4), setup_param_1 (+0x54, 4), hit_part_count (+0x68, 8), unknown_78 (+0x78, 4), unknown_b0 (+0xb0, 8), unknown_c0 (+0xc0, 1)

## ComboModule (accessor +0xb8, 120 bytes)

Bytes: carried 18, recomputed 0, constant 72, handed over 0.

**carried** (6): combo_type* (+0x10, 4), count* (+0x14, 4), window_frame* (+0x18, 4), status_kind_at_set* (+0x1c, 4), window_hold* (+0x48, 1), enable_combo_input (+0x70, 1)

**constant** (7): vptr (+0x0, 8), owner_boma (+0x8, 8), uniq_combo_id_a (+0x20, 4), uniq_window_param_1 (+0x28, 16), uniq_window_param_2 (+0x38, 16), uniq_combo_id_b (+0x4c, 4), type6_window_param_1 (+0x50, 16)

**not touched** (1): type6_window_param_2 (+0x60, 16)

## AreaModule (accessor +0xc0, 784 bytes)

Bytes: carried 82, recomputed 22, constant 113, handed over 0.

**carried** (8): +0x48 byte (0 at construction) (+0x48, 1), whole (all areas on)* (+0x50, 1), module's own area instance (head of the CHILD-chained instances) (+0x220, 176), +0x2A0 (cleared on reset)* (+0x2a0, 2), +0x2A4..+0x2B4 (cleared on reset) (+0x2a4, 16), +0x2C0 vector (reset to a global constant vector)* (+0x2c0, 16), +0x2D0 counter (0 on reset)* (+0x2d0, 4), +0x304 flag (set by vtable +0x48 update)* (+0x304, 1)

**recomputed** (4): battle object id (0x50000000 = invalid)* (+0x4c, 4), +0x300 counter (0 on reset)* (+0x300, 4), battle object id A (0x50000000 = none)* (+0x308, 4), battle object id B (0x50000000 = none)* (+0x30c, 4)

**constant** (13): vptr (primary) (+0x0, 8), vptr (secondary base, vptr+0x208) (+0x8, 8), owner BattleObjectModuleAccessor (+0x10, 8), area entry table (container: +0x10 count, +0x18 array of 0x70-byte entries) (+0x18, 8), area contact log (container: +0x10 count, +0x18 array of 0x20-byte records) (+0x20, 8), water checker object (vtable 0x7104F69D18 default) (+0x28, 8), area param table (static default; +0x10 count, +0x18 array of 4 x u32 rows) (+0x38, 8), descriptor id (-1 default) (+0x40, 4), +0x51 byte (written while adding areas) (+0x51, 1), sleep state (0 awake, 1 sleeping, 2 wake pending)* (+0x54, 4), auto layer update (+0x58, 1), heap vector (begin/end/capacity), freed by initialize (+0x2d8, 24), +0x2F0 pair (zeroed by initialize) (+0x2f0, 16)

**not touched** (3): owned water checker (deleted on re-initialize) (+0x30, 8), module kind (6 at construction; descriptor +0x0) (+0x44, 4), per-area-kind blocks (11 = FIGHTER_AREA_KIND_NUM), pointer at block+0x10 zeroed (+0x60, 440)

## ItemModule (accessor +0xc8, 112 bytes)

Bytes: carried 12, recomputed 24, constant 74, handed over 0.

**carried** (4): pickable_item_kind* (+0x40, 4), have_item_visibility* (+0x65, 1), flag_0x68* (+0x68, 1), change_status_event (+0x6c, 1)

**recomputed** (7): pickable_item* (+0x48, 8), pickable_item_trait* (+0x50, 4), pickable_item_size* (+0x54, 4), pickable_flags_0x58* (+0x58, 2), pickable_value_0x5c* (+0x5c, 4), is_success_pickup_item* (+0x64, 1), is_success_auto_pickup_item* (+0x6d, 1)

**constant** (9): vptr (+0x0, 8), owner_boma (+0x8, 8), have_slot_num (+0x10, 8), have_slots (+0x18, 8), have_node_table (+0x20, 8), attach_items (+0x28, 8), pickup_context (+0x30, 8), pickup_callback (+0x38, 8), have_item_param_0x60 (+0x60, 4)

## LinkModule (accessor +0xd0, 336 bytes)

Bytes: carried 185, recomputed 16, constant 36, handed over 0.

**carried** (18): node_list_head* (+0x20, 8), node_list_tail* (+0x28, 8), node_count* (+0x30, 4), parent_list_head* (+0x38, 8), parent_list_tail* (+0x40, 8), parent_count* (+0x48, 4), manager_list_next (+0x50, 8), manager_list_prev (+0x58, 8), last_constraint_matrix (+0x70, 64), model_constraint_link_no* (+0xb0, 4), model_constraint_joint* (+0xb8, 8), model_constraint_target_joint* (+0xc0, 8), linked_attribute_mask (+0xc8, 4), link_attribute_mask (+0xcc, 4), constraint_rot_offset (+0xd0, 16), constraint_translate_offset* (+0xf0, 16), model_constraint_flag* (+0x144, 4), model_constraint_mutual* (+0x148, 1)

**recomputed** (1): constraint_scale_offset (+0xe0, 16)

**constant** (5): vptr (+0x0, 8), owner_boma (+0x8, 8), link_records (+0x18, 8), manager_list_owner (+0x60, 8), motion_transactor_link_object_id (+0x140, 4)

**not touched** (3): link_record_count (+0x10, 8), fixed_constraint_matrix (+0x100, 64), unknown_node_rot_suppress (+0x149, 1)

## TeamModule (accessor +0xd8, 80 bytes)

Bytes: carried 17, recomputed 0, constant 22, handed over 0.

**carried** (5): team_second_no* (+0x14, 4), hit_team_second_no* (+0x20, 4), team_no_copy (+0x28, 4), team_second_no_copy (+0x2c, 4), third_team_group_flag (+0x30, 1)

**constant** (6): vptr (+0x0, 8), team_no* (+0x10, 4), team_group_flag (+0x18, 1), hit_team_no* (+0x1c, 4), hit_team_group_flag (+0x24, 1), team_owner_id* (+0x34, 4)

**not touched** (7): owner_boma (+0x8, 8), team_owner_category (+0x38, 1), team_owner_kind (+0x3c, 4), team_owner_entry_id (+0x40, 4), team_owner_flag (+0x44, 1), metamon_owner_object_id (+0x48, 4), metamon_owner_fighter_entry_id* (+0x4c, 4)

## SearchModule (accessor +0xe0, 928 bytes)

Bytes: carried 139, recomputed 29, constant 138, handed over 0.

**carried** (13): shape_set.u30 (setup 1) (+0x30, 4), owner_object_id (0x50000000 = none) (+0x38, 4), shape_set.u48 / +0x4a u8 (+0x48, 4), group[0] (embedded collision group, vptr 0x7104f6aed8) (+0x50, 720), group.shapes (inline array of 64 shape pointers) (+0x80, 512), group.list_b (+ count u32 at +0x2a8) (+0x298, 16), active_part_num* (+0x330, 4), base_pos (object position) (+0x340, 16), pos (first vector of set_pos) (+0x360, 16), pos2 (second vector of set_pos) (+0x370, 16), invalid_attack_mask* (+0x390, 4), safe_pos_enabled (+0x39d, 1), pending_flag (+0x39e, 1)

**recomputed** (7): group.base_x (+0x2fc, 4), lr / scale (float of start and update) (+0x334, 4), situation* (+0x350, 4), float of start (s1) (+0x354, 4), pos_kind (int arg of set_pos, -1 = unset) (+0x380, 4), is_inflict* (+0x384, 4), flag_398 (cleared by slot 0x48) (+0x398, 1)

**constant** (17): vptr (+0x0, 8), owner (BattleObjectModuleAccessor) (+0x8, 8), group_count (=1) (+0x20, 8), groups (-> embedded group at +0x50, 0x2d0 bytes each) (+0x28, 8), shape_set.kind (setup 5, constructor -1) (+0x34, 4), shape_set.u3c (setup arg3; constructor 6) (+0x3c, 1), team_info (TeamModule slot 0x48 result) (+0x40, 8), group.list pointers (-> +0x298, +0x2c8, +0x2e0) (+0x2b0, 24), group.unique_id (+0x2f8, 4), part_count (search part capacity) (+0x320, 8), parts (array of 0x60-byte search parts) (+0x328, 8), check_interval (+0x388, 4), descriptor kind (setup descriptor +0x0; constructor 6) (+0x394, 4), remove_log_attack* (+0x399, 1), sleep (+0x39a, 1), sync_situation (+0x39b, 1), sync_lr (+0x39c, 1)

**not touched** (4): shape_set header (zeroed) (+0x10, 16), group.shape_vector.vptr (0x7104f6aef8) (+0x60, 8), group.list_a (empty: points to itself) + count u32 at +0x290 (+0x280, 16), check_interval_counter (+0x38c, 4)

## TurnModule (accessor +0xf0, 104 bytes)

Bytes: carried 33, recomputed 8, constant 42, handed over 0.

**carried** (10): direct_curve* (+0x38, 8), frame* (+0x40, 4), turn_lr* (+0x44, 4), turn_state* (+0x50, 4), hashed_curve* (+0x58, 8), change_lr* (+0x60, 1), lr_changed* (+0x61, 1), is_extern* (+0x62, 1), reversed* (+0x65, 1), motion_notified* (+0x66, 1)

**recomputed** (2): rot_y* (+0x48, 4), applied_rot_y* (+0x4c, 4)

**constant** (7): vptr (+0x0, 8), owner_boma (+0x8, 8), curve_map.buckets (+0x10, 8), curve_map.bucket_count (+0x18, 8), curve_map.first_node (+0x20, 8), omit_intermediate (+0x63, 1), mirror_by_lr (+0x64, 1)

**not touched** (2): curve_map.size (+0x28, 8), curve_map.max_load_factor (+0x30, 4)

## ReflectModule (accessor +0xf8, 56 bytes)

Bytes: carried 0, recomputed 5, constant 12, handed over 0.

**recomputed** (2): object_id* (+0x10, 4), flag_0x30 (reflected/hit marker)* (+0x30, 1)

**constant** (2): vptr (+0x0, 8), attack_mul* (+0x18, 4)

**not touched** (9): owner_boma (+0x8, 8), team_no* (+0x14, 4), speed_mul* (+0x1c, 4), life_mul* (+0x20, 4), count* (+0x24, 4), reverse_lr* (+0x28, 4), collision_no (+0x2c, 4), no_speed_mul (+0x31, 1), listen_second_event (+0x32, 1)

## ShieldModule (accessor +0x100, 184 bytes)

Bytes: carried 14, recomputed 35, constant 74, handed over 0.

**carried** (5): active_group_num* (+0x58, 4), owner_object_id (+0x60, 4), registered* (+0x7c, 1), hit_stop_mul* (+0x84, 4), hit_stop_slow (+0xb0, 1)

**recomputed** (9): hit_flag* (+0x7d, 1), hit_log_object_id_0* (+0x88, 4), hit_log_category_0* (+0x8c, 1), hit_log_90* (+0x90, 4), hit_log_object_id_1* (+0x94, 4), hit_log_category_1* (+0x98, 1), hit_log_9c* (+0x9c, 8), hit_log_object_ids_2* (+0xa4, 8), hit_log_ac* (+0xac, 4)

**constant** (14): vtable (+0x0, 8), owner_boma (+0x8, 8), groups (+0x18, 8), shield_num (+0x20, 8), shields (+0x28, 8), collision_group_num (+0x48, 8), collision_groups (+0x50, 8), collision_kind (+0x5c, 4), owner_category (+0x64, 1), team_info (+0x68, 8), unknown_70 (+0x70, 1), no_team (+0x71, 1), clear_logs_on_reset (+0x7e, 1), sleep (+0x7f, 1)

**not touched** (6): group_num* (+0x10, 8), shield_used_count (+0x30, 4), collision_list_node (+0x38, 16), unknown_72 (+0x72, 1), collision_category (+0x78, 4), attack_limit_mul (+0x80, 4)

## ReflectorModule (accessor +0x108, 184 bytes)

Bytes: carried 8, recomputed 40, constant 72, handed over 0.

**carried** (2): active_group_end* (+0x58, 4), owner_object_id (+0x60, 4)

**recomputed** (4): is_registered* (+0x7c, 1), is_hit* (+0x7d, 1), attack_limit_mul* (+0x80, 4), hit_info (+0x88, 40)

**constant** (13): vptr (+0x0, 8), owner_boma (+0x8, 8), groups (+0x18, 8), shape_num (+0x20, 8), shapes (+0x28, 8), collision_group_num (+0x48, 8), collision_groups (+0x50, 8), shield_kind (+0x5c, 4), team_info (+0x68, 8), flag_0x70 (+0x70, 1), no_team (+0x71, 1), flag_0x7e (+0x7e, 1), is_sleep (+0x7f, 1)

**not touched** (8): group_num* (+0x10, 8), active_shape_count (+0x30, 4), collision_list_node (+0x38, 16), owner_category (+0x64, 1), flag_0x72 (+0x72, 1), target_category_shift (+0x78, 4), hit_stop_mul (+0x84, 4), flag_0xb0 (+0xb0, 1)

## AbsorberModule (accessor +0x110, 184 bytes)

Bytes: carried 0, recomputed 40, constant 46, handed over 0.

**recomputed** (4): owner_object_id (+0x60, 4), is_registered* (+0x7c, 1), is_hit* (+0x7d, 1), hit_info (+0x88, 40)

**constant** (8): vptr (+0x0, 8), shape_num (+0x20, 8), shapes (+0x28, 8), collision_group_num (+0x48, 8), collision_groups (+0x50, 8), active_group_end (+0x58, 4), flag_0x7e (+0x7e, 1), is_sleep (+0x7f, 1)

**not touched** (15): owner_boma (+0x8, 8), group_num* (+0x10, 8), groups (+0x18, 8), active_shape_count (+0x30, 4), collision_list_node (+0x38, 16), shield_kind (+0x5c, 4), owner_category (+0x64, 1), team_info (+0x68, 8), flag_0x70 (+0x70, 1), no_team (+0x71, 1), flag_0x72 (+0x72, 1), target_category_shift (+0x78, 4), attack_limit_mul (+0x80, 4), hit_stop_mul (+0x84, 4), flag_0xb0 (+0xb0, 1)

## JostleModule (accessor +0x118, 128 bytes)

Bytes: carried 56, recomputed 12, constant 56, handed over 0.

**carried** (15): jostle_area (+0x10, 8), jostle_param (+0x18, 8), jostle_speed_x* (+0x20, 4), pos_z* (+0x2c, 4), overlap_x* (+0x30, 4), overlap_rate* (+0x34, 4), ignore_owner_id* (+0x3c, 4), force_gap (+0x44, 1), ignore_pri* (+0x46, 1), received_push_speed* (+0x50, 4), target_weight* (+0x58, 4), jostle_speed_part_a* (+0x5c, 4), jostle_speed_part_b* (+0x60, 4), status* (+0x73, 1), push_speed_x_set* (+0x78, 1)

**recomputed** (5): contact_state* (+0x40, 2), gap* (+0x43, 1), jostle_kind* (+0x45, 1), propagate_push_speed* (+0x4c, 4), speed_attenuation_rate* (+0x54, 4)

**constant** (20): vptr (+0x0, 8), owner_boma (+0x8, 8), push_speed_x (+0x24, 4), push_speed_x_2 (+0x28, 4), push_speed_x_overlap_rate (+0x38, 4), priority* (+0x42, 1), team (+0x48, 4), weight* (+0x64, 4), influence_opponent_weight (+0x68, 1), flag_69 (+0x69, 1), overlap_rate_mul (+0x6c, 4), area_kind* (+0x70, 2), layer (+0x72, 1), fix (+0x74, 1), refer (+0x75, 1), is_sleep* (+0x76, 1), ignore_speed_x (+0x77, 1), propagate_push_speed (+0x79, 1), overlap_rate_status (+0x7a, 1), push_speed_mul (+0x7c, 4)

## CatchModule (accessor +0x120, 160 bytes)

Bytes: carried 5, recomputed 64, constant 25, handed over 0.

**carried** (2): catching* (+0x92, 1), grab_id_filter (+0x94, 4)

**recomputed** (13): catch_hit_pos* (+0x40, 16), catch_record_50* (+0x50, 8), target_object_id (+0x54, 4), catch_record_58* (+0x58, 8), target_part_id (+0x5f, 1), catch_record_60* (+0x60, 8), grab_id (+0x63, 1), catch_record_68* (+0x68, 2), candidate_list_next* (+0x70, 8), candidate_list_prev* (+0x78, 8), best_distance* (+0x88, 4), send_cut_event* (+0x90, 1), flag_93 (+0x93, 1)

**constant** (4): vptr (+0x0, 8), owner_boma (+0x8, 8), candidate_list_owner (+0x80, 8), force_grab_flag (+0x91, 1)

**not touched** (6): init_hash (+0x10, 8), catch_node (+0x18, 8), catch_node_2 (+0x20, 8), node_param (+0x28, 4), attack_id (+0x2c, 4), catch_record_head (+0x30, 16)

## CancelModule (accessor +0x128, 32 bytes)

Bytes: carried 6, recomputed 0, constant 24, handed over 0.

**carried** (3): situation_kind* (+0x18, 4), enable_cancel* (+0x1c, 1), cancel_locked* (+0x1d, 1)

**constant** (3): vptr (+0x0, 8), owner_boma (+0x8, 8), cancel_group_table (+0x10, 8)

## CaptureModule (accessor +0x138, 144 bytes)

Bytes: carried 53, recomputed 12, constant 50, handed over 0.

**carried** (10): catch_node* (+0x10, 8), captured_damage* (+0x34, 4), catch_node_pos* (+0x50, 16), capture_node_pos* (+0x60, 16), ignore_object_id* (+0x78, 4), send_cut_event* (+0x7c, 1), node_link* (+0x7d, 1), thrown_finish* (+0x81, 1), motion_hi_lw* (+0x83, 1), cut_pos_fixed* (+0x85, 1)

**recomputed** (6): motion_offset* (+0x2c, 4), motion_offset_lw* (+0x30, 4), thrown* (+0x7e, 1), update_pos (+0x7f, 1), reaction* (+0x80, 1), ignore_distance* (+0x84, 1)

**constant** (7): vptr (+0x0, 8), owner_boma (+0x8, 8), capture_node* (+0x18, 8), capture_node_offset (+0x40, 16), cut_node (+0x70, 8), flag_86 (+0x86, 1), catchable (+0x87, 1)

**not touched** (3): capture_node_2 (+0x20, 8), node_param (+0x28, 4), ignore_catching* (+0x82, 1)

## EffectModule (accessor +0x140, 264 bytes)

Bytes: carried 54, recomputed 22, constant 133, handed over 0.

**carried** (15): visible_all* (+0x2c, 1), slow_applied* (+0x2f, 1), embedded listener {vptr 0x7104f6cc80, ptr} (+0x38, 16), aux_pointers_50 (+0x50, 24), req_counter* (+0x78, 4), offset_to_next* (+0x7c, 4), common_effect_kind* (+0x90, 8), base_slow_rate {stop-affected, no-stop} (+0xb0, 8), slow_rate_mul (+0xb8, 4), slow_rate_no_stop_mul (+0xbc, 4), system_disable_count* (+0xc0, 4), whole* (+0xde, 1), effect_disabled (stored inverted)* (+0xe2, 1), flag_e4 (+0xe4, 1), status_effect_killed* (+0xe5, 1)

**recomputed** (4): last_handle* (+0x24, 4), guard_mark_effect_kind* (+0xc8, 8), flag_dc* (+0xdc, 1), enable_ground_effect* (+0xe6, 1)

**constant** (22): vptr (+0x0, 8), owner_boma (+0x8, 8), screen_effect_objects (fill_screen / color_collection targets) (+0x10, 16), owner_effect_id (14-bit object serial | 0x1000000; also the match key of this object's live effects in the global effect list) (+0x20, 4), req_joint_or_group (-1) (+0x28, 4), sync_scale* (+0x2d, 1), visible_kind_flag (+0x2e, 1), effect_resource_container (+0x30, 8), flags_48 (u16 = 1, u8 +0x4A = 0) (+0x48, 3), emit_target {ptr +0x68, u32 +0x70} (+0x68, 12), common_effect (owned current 'common' effect object) (+0x80, 8), common_effect_set (ring buffer of Hash40 entries: count +0x10, capacity +0x8, start +0x18, data +0x28) (+0x88, 8), continual_effects {begin, end} (+0x98, 16), time_effects (+0xa8, 8), whole_attr_mask (+0xd8, 4), visible_applied (+0xdd, 1), sync_visibility* (+0xdf, 1), flag_e1 (+0xe1, 1), flag_e3 (+0xe3, 1), flag_e7 (+0xe7, 1), flag_e8 (+0xe8, 1), fighter_effect_registry {begin +0xF0, root +0xF8, size +0x100} (+0xf0, 24)

**not touched** (2): reflection_effect_kind (+0xd0, 8), flag_e0 (+0xe0, 1)

## SoundModule (accessor +0x148, 2144 bytes)

Bytes: carried 378, recomputed 351, constant 375, handed over 0.

**carried** (9): cached_se[11] {u64 se_label/handle +0, u32 handle_id +8 (-1)} (+0x28, 176), se_slot[16] {vptr +0x0, sound handle object +0x8, u32 label +0x10, u32 kind +0x14 (0x870065 = none), u8 flag +0x18, u64 -1 +0x20, f32 volume +0x28, u16 +0x38, ...} (+0xf8, 1280), status_se_slot[4] (+0x5f8, 320), voice_slot[2] (+0x738, 136), status_se_state {+0x7C8, +0x7D0} (+0x7c8, 8), auto_se_pitch* (+0x7cc, 4), play_inhibit {Hash40 +0x7E0, u32 frames +0x7E8} (+0x7e0, 12), flag_809* (+0x809, 1), fighter_voice_flags (+0x854..+0x85A) (+0x854, 7)

**recomputed** (2): default_handle (-1) (+0x18, 4), landing_se* (+0x7c0, 8)

**constant** (15): vptr (+0x0, 8), owner_boma (+0x8, 8), sound_player (per-object audio emitter) (+0x20, 8), position_nodes {+0xD8, +0xE0} (16-byte nodes: u64 0, u32 -1, u8 1) (+0xd8, 16), takeout_se* (+0x7d8, 8), pending_handle {object +0x7F0, id +0x7F8, flag +0x7FC} (+0x7f0, 13), pending_flag_800 (+0x800, 1), play_hit_se_flag* (+0x801, 1), no_hit_se* (+0x802, 1), takeout_se_status_flag* (+0x804, 1), flag_805 (+0x805, 1), gamespeed_se_calibration (+0x806, 1), fighter_820 (+0x820, 4), fighter_owned_list (+0x828..+0x848) (+0x828, 40), fighter_voice_state (+0x850, 4)

**not touched** (5): sound_owner_id (-1) (+0x10, 4), sound_owner_sub_id (+0x14, 4), value_7ec (+0x7ec, 4), stop_all_flags {+0x807, +0x808} (+0x807, 2), fighter_voice_ids {+0x80C, +0x810} (initial 0x00FFFFFF, 0x00FFFFFF) (+0x80c, 8)

## VisibilityModule (accessor +0x150, 136 bytes)

Bytes: carried 8, recomputed 0, constant 82, handed over 0.

**carried** (5): whole* (+0x10, 1), visibility_mode (+0x48, 4), groups_changed* (+0x80, 1), flag_81* (+0x81, 1), mesh_dirty* (+0x82, 1)

**constant** (10): vptr (+0x0, 8), owner_boma (+0x8, 8), model_visible (+0x11, 1), visible_sub_flag (+0x12, 1), visibility_desc (+0x18, 8), group_index_maps (+0x20, 8), group_states (+0x30, 8), part_resolver_callback (+0x38, 16), mesh_vector (+0x50, 24), group_mesh_lists (+0x68, 24)

**not touched** (1): init_arg1_word0 (+0x28, 8)

## GrabModule (accessor +0x158, 896 bytes)

Bytes: carried 86, recomputed 18, constant 153, handed over 0.

**carried** (8): active_num* (+0x20, 4), pos* (+0x30, 16), power_up* (+0x48, 4), collision_attr (+0x78, 4), owner_object_id (+0x80, 4), collision_group (+0x98, 720), rebound* (+0x370, 1), disable_sub_fighter (+0x372, 1)

**recomputed** (4): scale* (+0x40, 4), lr* (+0x4c, 4), update_pending (+0x36e, 1), flag_0x371 (+0x371, 1)

**constant** (15): vptr (+0x0, 8), owner_boma (+0x8, 8), grab_num (+0x10, 8), grabs (+0x18, 8), scale_2nd (+0x44, 4), size_mul (+0x50, 4), collision_group_num (+0x68, 8), collision_groups (+0x70, 8), target_category_shift (+0x7c, 4), owner_category (+0x84, 1), team_info (+0x88, 8), team_info_2 (+0x90, 8), grab_kind (+0x368, 4), check_front (+0x36d, 1), is_sleep (+0x36f, 1)

**not touched** (2): collision_list_node (+0x58, 16), is_active_flag (+0x36c, 1)

## SlopeModule (accessor +0x160, 200 bytes)

Bytes: carried 75, recomputed 20, constant 58, handed over 0.

**carried** (15): requested_kind_mask* (+0x10, 4), active_kind_mask* (+0x14, 4), request_list.count* (+0x30, 8), pending_request (+0x40, 16), slope_angle (+0x50, 4), body_blend (total, left) (+0x54, 8), left_foot_blend (total, left) (+0x5c, 8), right_foot_blend (total, left) (+0x64, 8), line_change_blend_frames (+0x6c, 4), ground_line (+0x70, 8), ground_line_ref (ptr, ctrl) (+0x78, 16), foot_joint_index (left, right) (+0xbc, 2), foot_adjust_done (left, right) (+0xbe, 2), no_angle_limit (+0xc0, 1), enable (+0xc1, 1)

**recomputed** (2): floor_diff_l* (+0x9c, 4), floor_diff_r* (+0xa0, 4)

**constant** (11): vptr (+0x0, 8), owner_boma (+0x8, 8), request_list.data (+0x38, 8), max_slope_angle (+0x88, 4), posture_rot_index (+0x8c, 4), disabled_kind_mask (+0x98, 4), leg_params (+0xa8, 8), foot_ray_angle_rad (+0xb0, 4), setup_param_3 (+0xb4, 4), setup_param_4 (+0xb8, 4), has_foot_joint (left, right) (+0xc2, 2)

**not touched** (4): unknown_18 (+0x18, 8), request_list.vptr (+0x20, 8), request_list.capacity (+0x28, 8), top_joint (+0x90, 8)

## ShakeModule (accessor +0x168, 128 bytes)

Bytes: carried 7, recomputed 8, constant 49, handed over 0.

**carried** (4): active_shake_count* (+0x28, 4), model_offset_applied* (+0x40, 1), new_entry_flag (copied into entry +0x3d) (+0x70, 1), ignore_slow (+0x71, 1)

**recomputed** (1): resource slot (zeroed with +0x50/+0x58) (+0x48, 8)

**constant** (7): vptr (+0x0, 8), owner (BattleObjectModuleAccessor) (+0x8, 8), entry_count (shake slots) (+0x10, 8), entries (array of 0x90-byte shake entries) (+0x18, 8), shake_param_source (setup arg2) (+0x20, 8), offset_enabled (+0x41, 1), shared_resource_b (ptr +0x60, control block +0x68) (+0x60, 16)

**not touched** (2): offset (+0x30, 16), shared_resource_a (ptr +0x50, control block +0x58) (+0x50, 16)

## SlowModule (accessor +0x170, 72 bytes)

Bytes: carried 24, recomputed 1, constant 32, handed over 0.

**carried** (9): rate* (+0x10, 4), skip* (+0x14, 1), whole_frame* (+0x18, 4), whole_slot* (+0x1c, 1), frame_accumulator* (+0x20, 4), total_mag* (+0x24, 4), mag_ignore_effect* (+0x28, 4), mags_dirty* (+0x40, 1), rate_from_link* (+0x41, 1)

**recomputed** (1): prev_skip* (+0x15, 1)

**constant** (4): vptr (+0x0, 8), owner_boma (+0x8, 8), entry_count (+0x30, 8), entries (+0x38, 8)

## +0x178 (accessor +0x178, ? bytes)

Bytes: carried 1364, recomputed 0, constant 144, handed over 0.

(no field names: carried byte ranges +0x2a4..+0x2a5, +0x2a6..+0x2a7, +0x2a8..+0x2a9, +0x2aa..+0x2ab, +0x300..+0x5a8, +0x600..+0x8a8)

## ShadowModule (accessor +0x180, 64 bytes)

Bytes: carried 7, recomputed 0, constant 45, handed over 0.

**carried** (4): draw_size* (+0x28, 4), draw_status* (+0x3a, 1), visible* (+0x3c, 1), on_ground* (+0x3d, 1)

**constant** (11): vptr (+0x0, 8), owner_boma (+0x8, 8), shadow_type (+0x10, 4), size_min (+0x18, 4), size_max (+0x1c, 4), ground_distance_scale (+0x20, 4), joint (+0x30, 8), draw_flag[ShadowDrawFlag] (+0x38, 2), scale_by_ground_distance (+0x3b, 1), ground_shadow_enable (+0x3e, 1), force_hide (+0x3f, 1)

**not touched** (2): size (+0x14, 4), offset_y (+0x24, 4)

## MotionAnimcmdModule (accessor +0x188, 16 bytes)

Bytes: carried 0, recomputed 0, constant 16, handed over 0.

**constant** (2): vptr (+0x0, 8), impl (MotionAnimcmd line state, 0x120 bytes) (+0x8, 8)

## LuaModule (accessor +0x190, 552 bytes)

Bytes: carried 10, recomputed 5, constant 64, handed over 0.

**carried** (2): line_enabled[LuaScriptLineID] (+0x1e8, 10), status_func_enabled[LuaScriptStatusFuncID] (+0x1f2, 22)

**recomputed** (1): execute_line (LuaScriptLineID currently executing)* (+0x1e4, 4)

**constant** (12): vptr (+0x0, 8), owner_boma (+0x8, 8), script_work_area (0x18D bytes zeroed by the builder) (+0x20, 397), battle_object_id (+0x1a8, 4), init_arg_kind (+0x1ac, 1), init_arg_line_set (+0x1b0, 4), boma_copy (+0x1b8, 8), init_arg_object (+0x1c0, 8), lua_agent (script agent bound to lua_thread) (+0x1d8, 8), is_initialized (agent running) (+0x1e0, 1), flag_1e1 (+0x1e1, 1), fighter_extra_block (+0x220, 8)

**not touched** (5): lua_thread (lua_State of this object's agent) (+0x10, 8), state_flag (1) (+0x18, 4), init_arg_secondary (+0x1b4, 4), reserved_zero (+0x1c8, 16), status_data (vector of 176-byte entries = 22 lua function references, one entry per status kind) (+0x208, 24)

## InkPaintModule (accessor +0x198, 224 bytes)

Bytes: carried 73, recomputed 16, constant 38, handed over 0.

**carried** (8): ink_map.first_node (singly linked, 0x18-byte nodes) (+0x20, 8), ink_map.size (+0x28, 8), last_paint_color_2 (+0x50, 16), last_painter_id (+0x60, 4), ink_total (cached)* (+0x68, 4), special_paint[1].active (+0xa0, 1), special_paint[1].color (+0xb0, 16), special_paint[1].timer (+0xc8, 4)

**recomputed** (1): last_paint_color (+0x40, 16)

**constant** (7): vptr (+0x0, 8), owner (BattleObjectModuleAccessor) (+0x8, 8), ink_map.buckets (+0x10, 8), ink_map.bucket_count (+0x18, 8), ink_map.max_load_factor (1.0) (+0x30, 4), special_paint[0].active (+0x70, 1), disabled (+0xd0, 1)

**not touched** (4): special_paint[0].color (+0x80, 16), special_paint[0].alpha (1.0) (+0x90, 4), special_paint[0].param (hash 0x1275d6a98a) (+0x94, 4), special_paint[0].id (+0x98, 4)

`*` = verified by the game.
