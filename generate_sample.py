import urllib.request
import cv2
import numpy as np
import moviepy.editor as mp
import os

def create_sample_video():
    print("Generating sample test video...")
    image_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a0/George_Clooney_2023.jpg/330px-George_Clooney_2023.jpg"
    image_path = "sample_face.jpg"
    video_path = "sample.mp4"
    audio_path = "sample_audio.wav"

    try:
        # 1. Download a public domain face image
        print("Downloading sample face image...")
        req = urllib.request.Request(image_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response, open(image_path, 'wb') as out_file:
            out_file.write(response.read())

        # 2. Generate a 3-second silent video from the image
        print("Creating video track...")
        img = cv2.imread(image_path)
        height, width, layers = img.shape
        # Ensure dimensions are even for x264
        if width % 2 != 0: width -= 1
        if height % 2 != 0: height -= 1
        img = cv2.resize(img, (width, height))

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        fps = 24
        duration = 3
        video_out = cv2.VideoWriter("temp_silent.mp4", fourcc, fps, (width, height))

        for _ in range(fps * duration):
            video_out.write(img)
        video_out.release()

        # 3. Generate a 3-second dummy audio track (440Hz sine wave)
        print("Creating audio track...")
        sample_rate = 44100
        t = np.linspace(0, duration, sample_rate * duration, False)
        tone = np.sin(440 * 2 * np.pi * t)
        
        # Convert to 16-bit PCM
        audio_data = np.int16(tone * 32767)
        import scipy.io.wavfile
        scipy.io.wavfile.write(audio_path, sample_rate, audio_data)

        # 4. Combine audio and video
        print("Combining tracks...")
        video_clip = mp.VideoFileClip("temp_silent.mp4")
        audio_clip = mp.AudioFileClip(audio_path)
        final_clip = video_clip.set_audio(audio_clip)
        final_clip.write_videofile(video_path, codec="libx264", audio_codec="aac", verbose=False, logger=None)
        
        # Cleanup
        video_clip.close()
        audio_clip.close()
        os.remove(image_path)
        os.remove("temp_silent.mp4")
        os.remove(audio_path)
        
        print(f"Success! Sample video created at {video_path}")

    except Exception as e:
        print(f"Failed to generate sample video: {e}")

if __name__ == "__main__":
    create_sample_video()
