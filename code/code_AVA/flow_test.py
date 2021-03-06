import os
CPU = False
if CPU:
    os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"   # see issue https://stackoverflow.com/questions/40690598/can-keras-with-tensorflow-backend-be-forced-to-use-cpu-or-gpu-at-will
    os.environ["CUDA_VISIBLE_DEVICES"] = ""  # This must be imported before keras

import tensorflow as tf
import utils
import voting
from flow_model import flow_create_model, compile_model
from flow_data import load_split, get_AVA_set
import time
from keras import backend as K
import numpy as np


def main():

    K.clear_session()

    root_dir = '../../data/AVA/files/'

    # Load list of action classes and separate them (from utils_stream)
    classes = utils.get_AVA_classes(root_dir + 'ava_action_list_custom.csv')

    # Parameters for training (batch size 32 is supposed to be the best?)
    # params = {'dim': (224, 224), 'batch_size': 32,
    #          'n_classes': len(classes['label_id']), 'n_channels': 20,
    #          'shuffle': False, 'nb_epochs': 200, 'model': 'resnet50', 'email': False,
    #          'freeze_all': True, 'conv_fusion': False}
    params = {'dim': (224, 224), 'batch_size': 64,
              'n_classes': len(classes['label_id']), 'n_channels': 10,
              'nb_epochs': 157, 'model': "inceptionv3", 'email': True,
              'freeze_all': True, 'conv_fusion': False, 'train_chunk_size': 2**10,
              'validation_chunk_size': 2**10}
    crop = False  # TODO Use crop flow or not
    # Get validation set from directory
    partition = {}
    partition['test'] = get_AVA_set(classes=classes, filename=root_dir + "AVA_Test_Custom_Corrected.csv", soft_sigmoid=True)

    time_str = time.strftime("%y%m%d%H%M", time.localtime())
    result_csv = "test_outputs/kinetics_init/output_test_flow_kineticsinit_" + time_str + ".csv"

    # Load trained model
    # flow_weights = "../models/flowcrop_resnet50_1807180022.hdf5"
    flow_weights = "../models/flow_kineticsinit_inceptionv3_1808290834.hdf5"
    model, keras_layer_names = flow_create_model(classes=classes['label_id'], model_name=params['model'], soft_sigmoid=True, image_shape=(224, 224), opt_flow_len=10, freeze_all=params['freeze_all'], conv_fusion=params['conv_fusion'])
    model = compile_model(model, soft_sigmoid=True)
    model.load_weights(flow_weights)

    print("Test set size: " + str(len(partition['test'])))

    # Load chunks
    test_splits = utils.make_chunks(original_list=partition['test'], size=len(partition['test']), chunk_size=2**10)

    # Test directories where pre-processed test files are
    #flow_dir = "/media/pedro/actv-ssd/flowcrop_test/"
    flow_dir = "/media/pedro/actv-ssd/flow_test/"

    test_chunks_count = 0

    pose_votes = {}
    obj_votes = {}
    human_votes = {}

    for row in partition['test']:
        row = row.split("@")
        i = row[0] + "@" + row[1] + "@" + str(row[2]) + "@" + str(row[3]) + "@" + str(row[4]) + "@" + str(row[5])
        pose_votes[i] = np.zeros(utils.POSE_CLASSES)
        obj_votes[i] = np.zeros(utils.OBJ_HUMAN_CLASSES)
        human_votes[i] = np.zeros(utils.HUMAN_HUMAN_CLASSES)

    with tf.device('/gpu:0'):
        for testIDS in test_splits:
            # TODO Technically it shouldnt return labels here (these are ground truth)

            #x_test_flow, y_test_pose, y_test_object, y_test_human = load_split(testIDS, None, params['dim'], params['n_channels'], "test", 10, False, encoding="rgb", soft_sigmoid=True, crop=crop)
            x_test_flow, y_test_pose, y_test_object, y_test_human = load_split(testIDS, None, params['dim'], params['n_channels'], "test", 5, False, encoding="rgb", soft_sigmoid=True, crop=crop)
            print("Predicting on chunk " + str(test_chunks_count) + "/" + str(len(test_splits)))

            predictions = model.predict(x_test_flow, batch_size=params['batch_size'], verbose=1)

            # Convert predictions to readable output and perform majority voting
            voting.pred2classes(testIDS, predictions, pose_votes, obj_votes, human_votes, thresh=0.4)
            x_test_flow = None
            test_chunks_count += 1

    # When you're done getting all the votes, write output csv
    with open(result_csv, "a") as output_file:
        for key in pose_votes:
            idx = key.split("@")
            actions = []
            pv = pose_votes[key]
            pose_vote = pv.argmax(axis=0) + 1
            actions.append(pose_vote)

            # Get 3 top voted object
            ov = obj_votes[key]
            top_three_obj_votes = ov.argsort()[-3:][::-1] + utils.POSE_CLASSES + 1
            for t in top_three_obj_votes:
                if t != 0:  # Often there might only be two top voted or one
                    actions.append(t)
            # Get 3 top voted human
            hv = human_votes[key]
            top_three_human_votes = hv.argsort()[-3:][::-1] + utils.POSE_CLASSES + utils.OBJ_HUMAN_CLASSES + 1
            for t in top_three_human_votes:
                if t != 0:  # Often there might only be two top voted or one
                    actions.append(t)

            video_name = idx[0]
            timestamp = idx[1]
            bb_topx = idx[2]
            bb_topy = idx[3]
            bb_botx = idx[4]
            bb_boty = idx[5]
            for a in actions:
                line = video_name + "," + timestamp + "," + bb_topx + "," + bb_topy + "," + bb_botx + "," + bb_boty + "," + str(a)
                output_file.write("%s\n" % line)

    if params['email']:
        utils.sendemail(from_addr='pythonscriptsisr@gmail.com',
                        to_addr_list=['pedro_abreu95@hotmail.com'],
                        subject='Finished prediction for flow (crop)',
                        message='Testing flow with following params: ' + str(params),
                        login='pythonscriptsisr@gmail.com',
                        password='1!qwerty')


if __name__ == '__main__':
    main()
