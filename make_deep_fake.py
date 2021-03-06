from argparse import ArgumentParser
import cv2
from required import load_checkpoints, make_animation
from create_video import search_face
import os


parser = ArgumentParser()
parser.add_argument('--image', default='data/1.jpg', help='path to image')
parser.add_argument('--video', default='data/1.mp4', help='path to video')
parser.add_argument('--out',   default=f'data/{len(os.listdir("data")) + 1}.mp4')
args = parser.parse_args()

cascade = cv2.CascadeClassifier(r'data/haarcascade.xml')

image = cv2.imread(args.image)
image = search_face(image, cascade)
# nn model work with rgb and 256 pix image
image = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2RGB), (256, 256))
image = image / 255
generator, kp_detector = load_checkpoints()

video = cv2.VideoCapture(args.video)

make_animation(image, video, generator, kp_detector, cascade, args.out, args.video)
video.release()
