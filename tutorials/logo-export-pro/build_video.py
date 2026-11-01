"""Assemble the silent Arabic walkthrough from native, shaped-text artwork."""
from pathlib import Path
import json
import math
import os
import shutil
import subprocess
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SCREENS = HERE / 'screens'
FFMPEG = os.environ.get('FFMPEG') or shutil.which('ffmpeg')
if not FFMPEG:
    raise SystemExit('Install FFmpeg or set FFMPEG to its executable path.')
OUTPUT = HERE / 'Logo-Export-Pro-Arabic-Tutorial.mp4'
FPS = 24
scenes = json.loads((SCREENS / 'scenes.json').read_text())
slides = [Image.open(SCREENS / s['image']).convert('RGB') for s in scenes]
width, height = slides[0].size
assert all(im.size == (1920, 1080) for im in slides)
total = sum(round(s['duration'] * FPS) for s in scenes)

def timestamp(frame):
    milliseconds = round(frame / FPS * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}'

subtitles = []
position = 0
for i, scene in enumerate(scenes):
    end = position + round(scene['duration'] * FPS)
    subtitles.append(f'{i + 1}\n{timestamp(position)} --> {timestamp(end)}\n{scene["title"]}\n')
    position = end
(HERE / 'Arabic-Chapters.srt').write_text('\n'.join(subtitles), encoding='utf-8')

# Small contact sheets are for layout verification; full-resolution slides stay editable.
for start in (0, 7):
    contact = Image.new('RGB', (1440, 4 * 405), '#101b2c')
    for n in range(start, min(start + 7, len(slides))):
        thumb = slides[n].resize((720, 405), Image.Resampling.LANCZOS)
        slot = n - start
        contact.paste(thumb, ((slot % 2) * 720, (slot // 2) * 405))
    contact.save(SCREENS / f'contact-{start // 7 + 1}.jpg', quality=92)

command = [FFMPEG, '-hide_banner', '-loglevel', 'error', '-y',
    '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{width}x{height}', '-r', str(FPS),
    '-i', 'pipe:0', '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '19',
    '-profile:v', 'high', '-level:v', '4.2', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
    '-metadata', 'title=Logo Export Pro — Arabic tutorial',
    '-metadata', 'comment=Silent animated walkthrough using the supplied logo and name; actual extension exports shown.',
    str(OUTPUT)]
process = subprocess.Popen(command, stdin=subprocess.PIPE)
global_frame = 0
try:
    for index, scene in enumerate(scenes):
        count = round(scene['duration'] * FPS)
        highlight = scene.get('highlight', [])
        for frame in range(count):
            t = frame / FPS
            if index and t < .5:
                image = Image.blend(slides[index - 1], slides[index], t / .5)
            else:
                image = slides[index].copy()
            draw = ImageDraw.Draw(image, 'RGBA')
            if highlight and t > .55:
                x, y, w, h = highlight
                pulse = .55 + .45 * math.sin(t * math.pi * 1.1) ** 2
                draw.rounded_rectangle((x, y, x + w, y + h), radius=13,
                    outline=(94, 219, 192, round(110 + 110 * pulse)), width=4)
                # Pointer arrives gently at the callout, then stays clear of the labels.
                u = min(1, max(0, (t - .6) / 1.0))
                ease = 1 - (1 - u) ** 3
                target = (x + w - 13, y + h - 14)
                px = 1238 + (target[0] - 1238) * ease
                py = 893 + (target[1] - 893) * ease
                if t < 4.8:
                    draw.ellipse((px - 19, py - 19, px + 19, py + 19), fill=(94,219,192,38))
                    draw.polygon([(px,py),(px+4,py+29),(px+11,py+21),(px+21,py+21)],
                                 fill=(247,250,255,255),outline=(11,19,33,255),width=2)
            draw.rounded_rectangle((100,1045,1820,1053),radius=4,fill=(47,61,83,255))
            end_x = 100 + 1720 * (global_frame + 1) / total
            draw.rounded_rectangle((100,1045,end_x,1053),radius=4,fill=(212,144,97,255))
            if index == len(scenes) - 1 and frame >= count - FPS:
                opacity = (count - 1 - frame) / FPS
                image = Image.blend(Image.new('RGB',image.size,'#0a101c'),image,max(0,opacity))
            process.stdin.write(image.tobytes())
            global_frame += 1
        print(f'Encoded scene {index + 1}/{len(scenes)}: {scene["title"]}', flush=True)
finally:
    process.stdin.close()
result = process.wait()
if result:
    raise SystemExit(result)
print(f'Completed {OUTPUT.name}: {total / FPS:.1f}s, {width}×{height}, {FPS}fps; no audio.',flush=True)
