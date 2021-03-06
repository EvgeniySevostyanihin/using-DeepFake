import yaml
import numpy as np
import torch
from model import Generator, KPDetector
from torch.nn.parallel.data_parallel import DataParallel
from scipy.spatial import ConvexHull
import cv2
from create_video import scale_image, best_frame
from tqdm import tqdm


def normalize_kp(kp_source, kp_driving, kp_driving_initial):

    source_area = ConvexHull(kp_source['value'][0].data.cpu().numpy()).volume
    driving_area = ConvexHull(kp_driving_initial['value'][0].data.cpu().numpy()).volume
    adapt_movement_scale = np.sqrt(source_area) / np.sqrt(driving_area)

    kp_new = {k: v for k, v in kp_driving.items()}

    kp_value_diff = (kp_driving['value'] - kp_driving_initial['value'])
    kp_value_diff *= adapt_movement_scale
    kp_new['value'] = kp_value_diff + kp_source['value']

    jacobian_diff = torch.matmul(kp_driving['jacobian'], torch.inverse(kp_driving_initial['jacobian']))
    kp_new['jacobian'] = torch.matmul(jacobian_diff, kp_source['jacobian'])

    return kp_new


def load_checkpoints():
    """
    load model from weight and yaml structure
    AliaksandrSiarohin/first-order-model
    """

    with open('data/vox-256.yaml') as f:
        config = yaml.load(f)

    generator = Generator(**config['model_params']['generator_params'],
                          **config['model_params']['common_params'])
    generator.cuda()

    kp_detector = KPDetector(**config['model_params']['kp_detector_params'],
                             **config['model_params']['common_params'])
    kp_detector.cuda()

    checkpoint = torch.load('data/vox-cpk.pth.tar')

    generator.load_state_dict(checkpoint['generator'])
    kp_detector.load_state_dict(checkpoint['kp_detector'])

    generator = DataParallel(generator)
    kp_detector = DataParallel(kp_detector)

    generator.eval()
    kp_detector.eval()

    return generator, kp_detector


def make_animation(image, video, generator, kp_detector, cascade, out_path, video_path):
    """
    iteration for video and write out from nn in new video with same fps
    """
    with torch.no_grad():

        source = torch.tensor(image[np.newaxis].astype(np.float32)).permute(0, 3, 1, 2)
        source = source.cuda()

        fps = video.get(cv2.CAP_PROP_FPS)
        codec = cv2.VideoWriter_fourcc(*'XVID')

        out = cv2.VideoWriter(out_path, codec, fps, (256, 256))

        kp_source = kp_detector(source)
        coord, initial = best_frame(video_path, cascade, initial=True)
        num_frame = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
        ret, frame = video.read()

        image = scale_image(initial, coord, coord[2], frame.shape, n=0.1)
        image = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2RGB), (256, 256))
        image = image / 255

        driving = torch.tensor(np.array(image)[np.newaxis].astype(np.float32)).permute(0, 3, 1, 2)

        kp_driving_initial = kp_detector(driving)

        for _ in tqdm(range(num_frame + 1)):

            frame = scale_image(frame, coord, coord[2], frame.shape)
            frame = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), (256, 256))
            frame = frame / 255
            driving = torch.tensor(np.array(frame)[np.newaxis].astype(np.float32)).permute(0, 3, 1, 2)

            driving = driving.cuda()
            kp_driving = kp_detector(driving)
            kp_norm = normalize_kp(kp_source=kp_source, kp_driving=kp_driving,
                                   kp_driving_initial=kp_driving_initial)
            predict = generator(source, kp_source=kp_source, kp_driving=kp_norm)

            predict = np.transpose(predict['prediction'].data.cpu().numpy(), [0, 2, 3, 1])[0]
            predict = cv2.cvtColor(predict, cv2.COLOR_BGR2RGB)
            predict = np.uint8(predict * 255)
            out.write(predict)

            ret, frame = video.read()
            if not ret:
                break

    out.release()
