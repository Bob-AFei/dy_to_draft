import re
import shutil
import uuid
import json
import time
from concurrent.futures import ThreadPoolExecutor

import wget
from moviepy.editor import AudioFileClip
from moviepy.video.VideoClip import ImageClip
from PIL import Image
import zipfile
import os
import logging
from pathlib import Path

from datetime import datetime
from modules.utils import cdn_to_s3, s3_to_cdn, upload_s3

from modules.script_to_draft_v2_keyframe import insert_keyframe


DRAFT_FOLDER = "./data/cut_draft/"
TEMP_FOLDER = "./temp/"


def get_duration(filename):
    audio = AudioFileClip(filename)
    delta_duration_time = audio.duration
    audio.close()  # 显式地关闭文件
    return delta_duration_time


def get_image_size(image_path):
    with Image.open(image_path) as img:
        return img.size


class CutDraft:
    def __init__(self, chapter_id, draft_name: str, user_path: str, caps, enable_key_frame, *args, **kwargs):
        logging.info("合成草稿, 后端发来的参数 = chapter_id: %s, draft_name: %s, user_path: %s, caps: %s, enable_key_frame: %s" % (chapter_id, draft_name, user_path, caps, enable_key_frame))

        self.chapter_id = chapter_id
        self.enable_key_frame = enable_key_frame
        prefix = datetime.now().strftime('%m月%d日%H时%M分')
        draft_name = draft_name.replace(" ", "")
        draft_name = prefix + "_" + draft_name
        self.draft_name = draft_name if draft_name else datetime.now().strftime('%m月%d日%H时%M分')
        self.user_raw_path = user_path
        self.caps = caps

        self.draft_uuid = str(uuid.uuid4()).upper()
        self.content_id = str(uuid.uuid4()).upper()
        self.create_time_stamp = int(time.time() * 1000)

        self.local_path = os.path.join(TEMP_FOLDER, self.draft_uuid)
        self.local_draft_path = os.path.join(self.local_path, self.draft_name)
        self.local_material_path = os.path.join(self.local_draft_path, "material")
        self.user_path = self.user_raw_path
        self.user_draft_path = os.path.join(self.user_path, draft_name)
        self.user_material_path = os.path.join(self.user_draft_path, "material")

    def prepare_local_folder(self):
        if not os.path.exists(self.local_draft_path):
            os.makedirs(self.local_draft_path)
        if not os.path.exists(self.local_material_path):
            os.makedirs(self.local_material_path)
        with open(os.path.join(self.local_path, "请将旁边的文件夹，复制到剪映草稿文件夹中.txt"), "w",
                  encoding='utf-8') as f:
            f.write(
                "请将旁边的文件夹（以片段命名的文件夹），复制到剪映草稿文件夹中，请勿修改内部任何结构，你的剪映草稿地址是：\n%s" % self.user_raw_path)

    def speeds_creator(self, speed_uuid):
        tmp_data = {
            "curve_speed": None,
            "id": speed_uuid,
            "mode": 0,
            "speed": 1.0,
            "type": "speed"
        }
        return tmp_data

    def beats_creator(self, uuid):
        tmp_data = {
            "ai_beats": {
                "beat_speed_infos": [],
                "beats_path": "",
                "beats_url": "",
                "melody_path": "",
                "melody_percents": [
                    0.0
                ],
                "melody_url": ""
            },
            "enable_ai_beats": False,
            "gear": 404,
            "gear_count": 0,
            "id": uuid,
            "mode": 404,
            "type": "beats",
            "user_beats": [],
            "user_delete_ai_beats": None
        }
        return tmp_data

    def audio_creator(self, duration, file_name, audio_uuid, local_material_id):
        return {
            "app_id": 0,
            "category_id": "",
            "category_name": "local",
            "check_flag": 1,
            "duration": duration,
            "effect_id": "",
            "formula_id": "",
            "id": audio_uuid,
            "intensifies_path": "",
            "local_material_id": local_material_id,
            "music_id": '',
            "name": file_name,
            "path": os.path.join(self.user_material_path, file_name),  # TODO 这里
            "request_id": "",
            "resource_id": "",
            "source_platform": 0,
            "team_id": "",
            "text_id": "",
            "tone_category_id": "",
            "tone_category_name": "",
            "tone_effect_id": "",
            "tone_effect_name": "",
            "tone_speaker": "",
            "tone_type": "",
            "type": "extract_music",
            "video_id": "",
            "wave_points": []
        }

    def sound_channel_mappings_creator(self, audio_channel_mapping_uuid):
        tmp_data = {
            "audio_channel_mapping": 0,
            "id": audio_channel_mapping_uuid,
            "is_config_open": False,
            "type": "none"
        }
        return tmp_data

    def meta_music_creator(self, music_uuid, duration, filename, filepath, create_time):
        tmp_data = {
            "create_time": int(create_time),
            "duration": duration,
            "extra_info": filename,
            "file_Path": filepath,
            "height": 0,
            "id": music_uuid,
            "import_time": int(time.time()),
            "import_time_ms": int(time.time() * 10 ** 6),
            "item_source": 1,
            "md5": "",
            "metetype": "music",
            "roughcut_time_range": {
                "duration": duration,
                "start": 0
            },
            "sub_time_range": {
                "duration": -1,
                "start": -1
            },
            "type": 0,
            "width": 0
        }
        return tmp_data

    def audio_segment_creator(self, material_uuid_list, duration, start_time,
                              audio_uuid,
                              audio_segment_uuid):
        tmp_data = {
            "cartoon": False,
            "clip": None,
            "common_keyframes": [],
            "enable_adjust": True,
            "enable_color_curves": True,
            "enable_color_wheels": True,
            "enable_lut": True,
            "enable_smart_color_adjust": False,
            "extra_material_refs": material_uuid_list,
            "group_id": "",
            "hdr_settings": None,
            "id": audio_segment_uuid,
            "intensifies_audio": False,
            "is_placeholder": False,
            "is_tone_modify": False,
            "keyframe_refs": [],
            "last_nonzero_volume": 1.0,
            "material_id": audio_uuid,
            "render_index": 0,
            "reverse": False,
            "source_timerange": {
                "duration": duration,
                "start": 0
            },
            "speed": 1.0,
            "target_timerange": {
                "duration": duration,
                "start": start_time
            },
            "template_id": "",
            "template_scene": "default",
            "track_attribute": 0,
            "track_render_index": 0,
            "uniform_scale": None,
            "visible": True,
            "volume": 1.0
        }
        return tmp_data

    def meta_video_creator(self, video_uuid, duration, filename, filepath, create_time, height, width):
        tmp_data = {
            "create_time": int(create_time),
            "duration": duration,
            "extra_info": filename,
            "file_Path": filepath,
            "height": height,
            "id": video_uuid,
            "import_time": int(time.time()),
            "import_time_ms": int(time.time() * 10 ** 6),
            "item_source": 1,
            "md5": "",
            "metetype": "photo",
            "roughcut_time_range": {
                "duration": -1,
                "start": -1
            },
            "sub_time_range": {
                "duration": -1,
                "start": -1
            },
            "type": 0,
            "width": width
        }
        return tmp_data

    def canvases_creator(self, uuid):
        tmp = {
            "album_image": "",
            "blur": 0.0,
            "color": "",
            "id": uuid,
            "image": "",
            "image_id": "",
            "image_name": "",
            "source_platform": 0,
            "team_id": "",
            "type": "canvas_color"
        }
        return tmp

    def animation_creator(self, uuid):
        tmp_ = {
            "animations": [],
            "id": uuid,
            "type": "sticker_animation"
        }
        return tmp_

    def video_segement_creator(self, material_uuid_list, duration, start_time, video_uuid,
                               video_segment_uuid):
        tmp_data = {
            "cartoon": False,
            "clip": {
                "alpha": 1.0,
                "flip": {
                    "horizontal": False,
                    "vertical": False
                },
                "rotation": 0.0,
                "scale": {
                    "x": 1,
                    "y": 1
                },
                "transform": {
                    "x": 0.0,
                    "y": 0.0
                }
            },
            "common_keyframes": [],
            "enable_adjust": True,
            "enable_color_curves": True,
            "enable_color_wheels": True,
            "enable_lut": True,
            "enable_smart_color_adjust": False,
            "extra_material_refs": material_uuid_list,
            "group_id": "",
            "hdr_settings": {
                "intensity": 1.0,
                "mode": 1,
                "nits": 1000
            },
            "id": video_segment_uuid,
            "intensifies_audio": False,
            "is_placeholder": False,
            "is_tone_modify": False,
            "keyframe_refs": [],
            "last_nonzero_volume": 1.0,
            "material_id": video_uuid,
            "render_index": 0,
            "reverse": False,
            "source_timerange": {
                "duration": duration,
                "start": start_time
            },
            "speed": 1.0,
            "target_timerange": {
                "duration": duration,
                "start": start_time
            },
            "template_id": "",
            "template_scene": "default",
            "track_attribute": 0,
            "track_render_index": 0,
            "uniform_scale": {
                "on": True,
                "value": 1.0
            },
            "visible": True,
            "volume": 1.0
        }
        return tmp_data

    def video_creator(self, duration, file_name, video_uuid, height, width):
        tmp_data = {
            "audio_fade": None,
            "cartoon_path": "",
            "category_id": "",
            "category_name": "",
            "check_flag": 63487,
            "crop": {
                "lower_left_x": 0.0,
                "lower_left_y": 1.0,
                "lower_right_x": 1.0,
                "lower_right_y": 1.0,
                "upper_left_x": 0.0,
                "upper_left_y": 0.0,
                "upper_right_x": 1.0,
                "upper_right_y": 0.0
            },
            "crop_ratio": "free",
            "crop_scale": 1.0,
            "duration": duration,
            "extra_type_option": 0,
            "formula_id": "",
            "freeze": None,
            "gameplay": None,
            "has_audio": False,
            "height": height,
            "id": video_uuid,
            "intensifies_audio_path": "",
            "intensifies_path": "",
            "is_ai_generate_content": False,
            "is_unified_beauty_mode": False,
            "local_id": "",
            "local_material_id": "",
            "material_id": "",
            "material_name": file_name,
            "material_url": "",
            "matting": {
                "flag": 0,
                "has_use_quick_brush": False,
                "has_use_quick_eraser": False,
                "interactiveTime": [],
                "path": "",
                "strokes": []
            },
            "media_path": "",
            "object_locked": None,
            "origin_material_id": "",
            "path": os.path.join(self.user_material_path, file_name),  # TODO 这里
            "picture_from": "none",
            "picture_set_category_id": "",
            "picture_set_category_name": "",
            "request_id": "",
            "reverse_intensifies_path": "",
            "reverse_path": "",
            "source_platform": 0,
            "stable": None,
            "team_id": "",
            "type": "photo",
            "video_algorithm": {
                "algorithms": [],
                "deflicker": None,
                "motion_blur_config": None,
                "noise_reduction": None,
                "path": "",
                "time_range": None
            },
            "width": width
        }
        return tmp_data

    def text_segment_creator(self, material_uuid_list, duration, start_time,
                             text_uuid,
                             text_segment_uuid):
        tmp_data = {
            "cartoon": False,
            "clip": {
                "alpha": 1,
                "flip": {
                    "horizontal": False,
                    "vertical": False
                },
                "rotation": 0,
                "scale": {
                    "x": 1,
                    "y": 1
                },
                "transform": {
                    "x": 0,
                    "y": -0.7
                }
            },
            "common_keyframes": [],
            "enable_adjust": False,
            "enable_color_curves": True,
            "enable_color_wheels": True,
            "enable_lut": False,
            "enable_smart_color_adjust": False,
            "extra_material_refs": material_uuid_list,
            "group_id": "",
            "hdr_settings": None,
            "id": text_segment_uuid,
            "intensifies_audio": False,
            "is_placeholder": False,
            "is_tone_modify": False,
            "keyframe_refs": [],
            "last_nonzero_volume": 1.0,
            "material_id": text_uuid,
            "render_index": 0,
            "reverse": False,
            "source_timerange": None,
            "speed": 1.0,
            "target_timerange": {
                "duration": duration,
                "start": start_time
            },
            "template_id": "",
            "template_scene": "default",
            "track_attribute": 0,
            "track_render_index": 0,
            "uniform_scale": {
                "on": True,
                "value": 1
            },
            "visible": True,
            "volume": 1.0
        }
        return tmp_data

    def text_creator(self, content, text_uuid):
        tmp_data = {
            "add_type": 0,
            "alignment": 1,
            "background_alpha": 1,
            "background_color": "",
            "background_height": 0.14,
            "background_horizontal_offset": 0,
            "background_round_radius": 0,
            "background_style": 0,
            "background_vertical_offset": 0,
            "background_width": 0.14,
            "bold_width": 0,
            "border_color": "#000000",
            "border_width": 0.08,
            "check_flag": 15,
            "combo_info": {
                "text_templates": [

                ]
            },
            "content": "{\"text\":\"%s\",\"styles\":[{\"strokes\":[{\"content\":{\"solid\":{\"color\":[0,0,0]}},\"width\":0.08}],\"size\":7,\"fill\":{\"content\":{\"solid\":{\"color\":[1,0.870588,0]}}},\"range\":[0,%d]}]}" % (content, len(content)),
            "fixed_height": -1,
            "fixed_width": 600,
            "font_category_id": "",
            "font_category_name": "",
            "font_id": "",
            "font_name": "",
            "font_path": "",
            "font_resource_id": "",
            "font_size": 7,
            "font_source_platform": 0,
            "font_team_id": "",
            "font_title": "none",
            "font_url": "",
            "fonts": [

            ],
            "force_apply_line_max_width": False,
            "global_alpha": 1,
            "group_id": "",
            "has_shadow": False,
            "id": text_uuid,
            "initial_scale": 1,
            "is_rich_text": False,
            "italic_degree": 0,
            "ktv_color": "",
            "language": "",
            "layer_weight": 1,
            "letter_spacing": 0,
            "line_spacing": 0.02,
            "name": "",
            "preset_category": "",
            "preset_category_id": "",
            "preset_has_set_alignment": False,
            "preset_id": "",
            "preset_index": 0,
            "preset_name": "",
            "recognize_type": 0,
            "relevance_segment": [

            ],
            "shadow_alpha": 0.8,
            "shadow_angle": -45,
            "shadow_color": "#000000",
            "shadow_distance": 8,
            "shadow_point": {
                "x": 1.0182337649086284,
                "y": -1.0182337649086284
            },
            "shadow_smoothing": 1,
            "shape_clip_x": False,
            "shape_clip_y": False,
            "style_name": "黄字黑边",
            "sub_type": 0,
            "text_alpha": 1,
            "text_color": "#ffde00",
            "text_preset_resource_id": "",
            "text_size": 30,
            "text_to_audio_ids": [

            ],
            "tts_auto_update": False,
            "type": "text",
            "typesetting": 0,
            "underline": False,
            "underline_offset": 0.22,
            "underline_width": 0.05,
            "use_effect_default_color": True,
            "words": {
                "end_time": [

                ],
                "start_time": [

                ],
                "text": [

                ]
            }
        }
        return tmp_data

    def _init_draft(self):
        # 创建目标目录如果它不存在
        if not os.path.exists(self.local_draft_path):
            os.makedirs(self.local_draft_path)

        # 复制所有模板json
        for item in os.listdir(DRAFT_FOLDER):
            s = os.path.join(DRAFT_FOLDER, item)
            d = os.path.join(self.local_draft_path, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)

        with open(os.path.join(self.local_draft_path, 'draft_content.json'), 'r', encoding='utf-8') as f:
            self.draft_content = json.load(f)
        with open(os.path.join(self.local_draft_path, 'draft_meta_info.json'), 'r', encoding='utf-8') as f:
            self.draft_meta_info = json.load(f)

        self.width = 1280
        self.height = 960
        try:
            # 读取caps第一个元素的图片地址，获取分辨率，设置为width、height
            imageItem0Url = self.caps[0]['image_url']
            imageItem0TempPath = os.path.join(self.local_draft_path, "imageItem0Temp.jpg")
            wget.download(cdn_to_s3(imageItem0Url), imageItem0TempPath, bar=None)
            imageItem0Temp = ImageClip(imageItem0TempPath)
            self.width = imageItem0Temp.w
            self.height = imageItem0Temp.h
            logging.info(f"剪映草稿分辨率: {self.width} x {self.height}")
            # 删除临时文件
            os.remove(imageItem0TempPath)
            logging.info(f"删除临时文件: {imageItem0TempPath}")
        except:
            import traceback
            logging.error(f"获取分辨率失败: {traceback.format_exc()}")
            self.width = 1280
            self.height = 960

        self.draft_content['id'] = str(uuid.uuid4()).upper()
        self.draft_content['canvas_config']['height'] = self.height
        self.draft_content['canvas_config']['width'] = self.width
        self.draft_content['materials']['audios'] = []
        self.draft_content['materials']['beats'] = []
        self.draft_content['materials']['canvases'] = []
        self.draft_content['materials']['material_animations'] = []
        self.draft_content['materials']['sound_channel_mappings'] = []
        self.draft_content['materials']['speeds'] = []
        self.draft_content['tracks'] = []

        self.draft_meta_info['draft_id'] = str(uuid.uuid4()).upper()
        self.draft_meta_info['draft_fold_path'] = self.user_draft_path
        self.draft_meta_info['draft_root_path'] = self.user_path
        self.draft_meta_info['draft_name'] = self.draft_name
        self.draft_meta_info['tm_draft_create'] = int(time.time() * 10 ** 6)
        self.draft_meta_info['tm_draft_modified'] = int(time.time() * 10 ** 6)
        self.draft_meta_info['draft_materials'][0]['value'] = []
        self.draft_meta_info['draft_removable_storage_device'] = ""
        self.total_duration = 0

        if self.user_draft_path.startswith("/"):
            self.draft_content['last_modified_platform']['os'] = 'mac'
            self.draft_content['last_modified_platform']['os_version'] = '12.3.1'

    def _download_with_retry(self, url, path, max_retries=3):
        retries = 0
        url = cdn_to_s3(url)
        while retries < max_retries:
            try:
                wget.download(url, path, bar=None)
                return True  # 返回 True 表示下载成功
            except Exception as e:
                print(f"下载失败，正在重试... ({retries + 1}/{max_retries})")
                retries += 1
                time.sleep(1)
        print(f"下载失败，已达到最大重试次数：{url}")
        return False  # 返回 False 表示下载失败

    def _download_single_material(self, cap, index):
        # 下载单个素材的函数
        image_path = os.path.join(self.local_material_path, '%d.jpg' % index)
        audio_path = os.path.join(self.local_material_path, '%d.mp3' % index)

        # 下载图片，带重试
        image_result = self._download_with_retry(cap['image_url'], image_path)
        # 下载音频，带重试
        audio_result = self._download_with_retry(cap['audio_url'], audio_path)

        # 返回一个元组，包含索引和两个下载结果
        return (index, image_result, audio_result)

    def _download_mats(self):
        # 计算下载耗时
        start_time = time.time()

        # 使用线程池执行下载
        with ThreadPoolExecutor(max_workers=8) as executor:
            # 创建一个future列表
            futures = [executor.submit(self._download_single_material, cap, i) for i, cap in enumerate(self.caps)]
            # 收集结果
            results = [future.result() for future in futures]  # 这里会等待每个线程完成，并收集结果

        end_time = time.time()
        print("下载素材耗时: %s" % (end_time - start_time))

        # 处理结果
        for result in results:
            index, image_result, audio_result = result
            if not image_result or not audio_result:
                print(f"下载失败的素材索引: {index}")

    def _add_tracks(self):

        start_time = 0
        total_time = 0
        n = 0

        # 创建多媒体track
        track_audio_uuid = str(uuid.uuid4()).upper()
        track_video_uuid = str(uuid.uuid4()).upper()
        track_text_uuid = str(uuid.uuid4()).upper()

        tmp_video_track = dict(attribute=0, flag=0, id=track_video_uuid, segments=[], type="video")
        tmp_audio_track = dict(attribute=0, flag=0, id=track_audio_uuid, segments=[], type="audio")
        tmp_text_track = dict(attribute=0, flag=0, id=track_text_uuid, segments=[], type="text")

        for i, cap in enumerate(self.caps):

            image_name = "%d.jpg" % i
            audio_name = "%d.mp3" % i

            local_image_path = os.path.join(self.local_material_path, image_name)
            local_audio_path = os.path.join(self.local_material_path, audio_name)

            user_image_path = os.path.join("./material", image_name)
            user_audio_path = os.path.join("./material", audio_name)  # TODO: 这里这里！

            # 这一步处理音频信息
            stat = os.stat(local_audio_path)
            mp3file_create_time = stat.st_ctime

            try:
                # 获取音频时长，单位是微秒，加5000是为了防止精度丢失
                delta_duration = int(get_duration(local_audio_path) * 10 ** 6 + 33333)
            except:
                delta_duration = 0

            # 处理draft_content文件
            audio_uuid = str(uuid.uuid4()).upper()
            sound_channel_mapping_uuid = str(uuid.uuid4()).upper()
            speed_uuid = str(uuid.uuid4()).upper()
            beats_uuid = str(uuid.uuid4()).upper()
            audio_segment_uuid = str(uuid.uuid4()).upper()

            # 创建与meta文件关联ID并将其写入meta
            music_id = str(uuid.uuid4())
            tmp_music = self.meta_music_creator(music_id, duration=delta_duration, filepath=user_audio_path,
                                                filename=audio_name, create_time=mp3file_create_time)

            self.draft_meta_info['draft_materials'][0]['value'].append(tmp_music)

            tmp_sound_channel_mapping = self.sound_channel_mappings_creator(sound_channel_mapping_uuid)
            tmp_speed = self.speeds_creator(speed_uuid)
            tmp_beat = self.beats_creator(beats_uuid)
            tmp_audio = self.audio_creator(delta_duration, audio_name, audio_uuid, music_id)

            self.draft_content['materials']['sound_channel_mappings'].append(tmp_sound_channel_mapping)
            self.draft_content['materials']['speeds'].append(tmp_speed)
            self.draft_content['materials']['beats'].append(tmp_beat)
            self.draft_content['materials']['audios'].append(tmp_audio)

            tmp_audio_segment = self.audio_segment_creator(
                material_uuid_list=[sound_channel_mapping_uuid, speed_uuid, beats_uuid],
                duration=delta_duration, start_time=start_time,
                audio_uuid=audio_uuid, audio_segment_uuid=audio_segment_uuid)

            # 这一步处理图片信息
            canvas_uuid = str(uuid.uuid4()).upper()
            material_animation_uuid = str(uuid.uuid4()).upper()
            tmp_canvas = self.canvases_creator(canvas_uuid)
            tmp_animation = self.animation_creator(material_animation_uuid)
            tmp_video_uuid = str(uuid.uuid4()).upper()

            # 获取图片信息
            width, height = get_image_size(local_image_path)
            stat = os.stat(local_image_path)
            imgfile_create_time = stat.st_ctime

            meta_video = self.meta_video_creator(create_time=imgfile_create_time, video_uuid=tmp_video_uuid,
                                                 duration=delta_duration, filename=image_name,
                                                 filepath=user_image_path, height=height, width=width)

            self.draft_meta_info['draft_materials'][0]['value'].append(meta_video)

            tmp_video = self.video_creator(duration=delta_duration, file_name=image_name, video_uuid=tmp_video_uuid,
                                           height=int(height), width=int(width))

            self.draft_content['materials']['material_animations'].append(tmp_animation)
            self.draft_content['materials']['canvases'].append(tmp_canvas)
            self.draft_content['materials']['videos'].append(tmp_video)

            # 关键帧UUID
            video_segment_uuid = str(uuid.uuid4()).upper()
            tmp_video_segment = self.video_segement_creator([canvas_uuid, speed_uuid, material_animation_uuid],
                                                            duration=delta_duration, start_time=start_time,
                                                            video_uuid=tmp_video_uuid,
                                                            video_segment_uuid=video_segment_uuid)

            tmp_animation = self.animation_creator(material_animation_uuid)
            self.draft_content['materials']['material_animations'].append(tmp_animation)
            
            # 这一步是处理字幕
            content = cap['content_split']

            # 切割字幕为多个小字幕
            sentences = re.split('。|,|，|！|\!|\.|？|\?|“|：|”', content)
            while '' in sentences: sentences.remove('')
            text_start_time = start_time
            for sentence in sentences:
                # text_start_time是当前小字幕的开始时间
                # 当前小字幕的时长
                text_duration = delta_duration * len(sentence) / len(''.join(sentences))
                # sentence为当前小字幕
                text_uuid = str(uuid.uuid4()).upper()
                tmp_text = self.text_creator(sentence, text_uuid)
                self.draft_content['materials']['texts'].append(tmp_text)
                # 添加到text的track中
                text_segment_uuid = str(uuid.uuid4()).upper()
                tmp_text_segment = self.text_segment_creator([tmp_animation],
                                                            duration=text_duration, start_time=text_start_time,
                                                            text_uuid=text_uuid, text_segment_uuid=text_segment_uuid)
                # text
                tmp_text_track['segments'].append(tmp_text_segment)
                # 更新时间
                text_start_time += text_duration

            # video
            tmp_video_track['segments'].append(tmp_video_segment)
            # audio
            tmp_audio_track['segments'].append(tmp_audio_segment)

            start_time = start_time + delta_duration
            total_time = total_time + delta_duration
            n += 1

        self.total_duration = total_time
        self.draft_meta_info['tm_duration'] = self.total_duration
        self.draft_content['duration'] = self.total_duration
        self.draft_content['tracks'].append(tmp_video_track)
        self.draft_content['tracks'].append(tmp_audio_track)
        self.draft_content['tracks'].append(tmp_text_track)

    def _save_draft(self):
        with open(os.path.join(self.local_draft_path, 'draft_content.json'), 'w', encoding='utf-8') as f:
            json.dump(self.draft_content, f, ensure_ascii=False)
        with open(os.path.join(self.local_draft_path, 'draft_meta_info.json'), 'w', encoding='utf-8') as f:
            json.dump(self.draft_meta_info, f, ensure_ascii=False)

    def _zip_and_upload_draft(self):
        zip_file_name = datetime.now().strftime('%m月%d日%H时%M分')
        zip_file_path = os.path.join(self.local_path, f"{zip_file_name}.zip")
        with zipfile.ZipFile(zip_file_path, 'w') as zfile:
            for folder_name, _, files in os.walk(self.local_path):
                relative_folder_path = os.path.relpath(folder_name, self.local_path)
                if relative_folder_path != ".":
                    zfile.write(folder_name, relative_folder_path)
                for item_file in files:
                    if item_file == f"{zip_file_name}.zip":
                        continue
                    file_path = os.path.join(folder_name, item_file)
                    relative_file_path = os.path.join(relative_folder_path, item_file)
                    zfile.write(file_path, relative_file_path)
        # 上传到s3
        print("zip压缩成功，准备上传到S3 zip_file_path = " + zip_file_path)
        uri = upload_s3(zip_file_path, 'application/zip')
        print("zip上传成功，uri = " + uri)
        return uri

    def _remove_folder(self):
        # 删除本地文件
        shutil.rmtree(self.local_path)
        pass

    def create_daft(self):
        print("开始合成草稿")
        try:
            # 准备文件夹
            self.prepare_local_folder()
            # 初始化草稿模版数据
            self._init_draft()
            # 下载素材
            self._download_mats()
            # 添加轨道数据
            self._add_tracks()
            # 保存轨道数据
            self._save_draft()
            # 添加随机关键帧
            if self.enable_key_frame == 1:
                insert_keyframe(os.path.join(self.local_draft_path, 'draft_content.json'), 1.3)
            # 压缩并上传
            uri = self._zip_and_upload_draft()
            # 删除临时文件
            self._remove_folder()
            logging.info("任务%s, 任务名%s, 生成成功draft: %s" % (self.chapter_id, self.draft_name, uri))
            return uri
        except:
            # 删除临时文件
            self._remove_folder()
            import traceback
            logging.error("任务%s, 任务名%s, 生成失败: %s" % (self.chapter_id, self.draft_name, traceback.format_exc()))
            return ""


if __name__ == '__main__':
    # caps = [
    #     {"image_url": '../data/material/0.jpg',
    #      "audio_url": '../data/material/0.mp3',
    #      "content_split": '这是台词11111111111111111111111'},
    #     {"image_url": '../data/material/1.jpg',
    #      "audio_url": '../data/material/1.mp3',
    #      "content_split": '这是台词22222222222222222222222'},
    #     {"image_url": '../data/material/2.jpg',
    #      "audio_url": '../data/material/2.mp3',
    #      "content_split": '这是台词33333333333333333333333'},
    # ]
    # 计算耗时
    start_time_1 = time.time()
    # 读取json文件解析到caps
    with open('../data/json/draft.json', 'r', encoding='utf-8') as f:
        json_data = json.load(f)
    draft = CutDraft(str(json_data.get("chapter_id")),
                     str(json_data.get("uid")),
                     r"C:\Users\Kudou\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft",
                     json_data.get("caps"))
    zipPath = draft.create_daft()
    print("总耗时: %s" % (time.time() - start_time_1))
    print('合成完毕，path = ' + zipPath)
