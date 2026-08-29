"""
Synthetic Sample Video Generator for Quick Local Pipeline Verification
======================================================================
Downloads a public face image and creates a 3-second sample MP4 with audio
to verify end-to-end video ingestion without downloading large external test files.

Run: python scripts/generate_sample.py
"""
import os
import sys
import urllib.request
import cv2
import numpy as np

# Add workspace root to sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

def create_sample_video(output_video="sample.mp4"):
    if not os.path.isabs(output_video):
        output_video = os.path.join(ROOT_DIR, output_video)

    print(f"Generating synthetic verification video: {output_video}")
    image_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a0/George_Clooney_2023.jpg/330px-George_Clooney_2023.jpg"
    image_path = os.path.join(ROOT_DIR, "temp", "sample_face.jpg")
    audio_path = os.path.join(ROOT_DIR, "temp", "sample_audio.wav")
    temp_silent = os.path.join(ROOT_DIR, "temp", "temp_silent.mp4")

    os.makedirs(os.path.join(ROOT_DIR, "temp"), exist_ok=True)

    try:
        # 1. Download sample face image
        print("1. Downloading sample face image...")
        req = urllib.request.Request(image_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req) as response, open(image_path, 'wb') as out_file:
            out_file.write(response.read())

        # 2. Generate 3-second silent video
        print("2. Generating video frames...")
        img = cv2.imread(image_path)
        height, width, _ = img.shape
        if width % 2 != 0: width -= 1
        if height % 2 != 0: height -= 1
        img = cv2.resize(img, (width, height))

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        fps = 24
        duration = 3
        video_out = cv2.VideoWriter(temp_silent, fourcc, fps, (width, height))
        for _ in range(fps * duration):
            video_out.write(img)
        video_out.release()

        # 3. Generate 3-second audio track (440Hz sine wave)
        print("3. Generating audio track...")
        sample_rate = 44100
        t = np.linspace(0, duration, sample_rate * duration, False)
        tone = np.sin(440 * 2 * np.pi * t)
        audio_data = np.int16(tone * 32767)
        import scipy.io.wavfile
        scipy.io.wavfile.write(audio_path, sample_rate, audio_data)

        # 4. Combine audio and video
        print("4. Combining audio and video...")
        try:
            from moviepy import VideoFileClip, AudioFileClip
        except ImportError:
            import moviepy.editor as mp
            VideoFileClip = mp.VideoFileClip
            AudioFileClip = mp.AudioFileClip

        video_clip = VideoFileClip(temp_silent)
        audio_clip = AudioFileClip(audio_path)
        final_clip = video_clip.with_audio(audio_clip) if hasattr(video_clip, "with_audio") else video_clip.set_audio(audio_clip)
        final_clip.write_videofile(output_video, codec="libx264", audio_codec="aac", verbose=False, logger=None)

        video_clip.close()
        audio_clip.close()

        # Cleanup
        for p in [image_path, temp_silent, audio_path]:
            if os.path.exists(p):
                os.remove(p)

        print(f"[✓] Success! Sample video created at: {output_video}")

    except Exception as e:
        print(f"[✗] Failed to generate sample video: {e}")

if __name__ == "__main__":
    create_sample_video()
