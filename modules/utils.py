import math
from collections import defaultdict

import numpy as np
import torch


class ConllSent(object):
    """docstring for ConllSent"""

    def __init__(self, key_list=["word", "tag", "head"]):
        super(ConllSent, self).__init__()
        self.sent_dict = {}
        self.keys = key_list
        for key in key_list:
            self.sent_dict[key] = []

    def __getitem__(self, key):
        return self.sent_dict[key]

    def __setitem__(self, key, item):
        self.sent_dict[key] = item

    def __len__(self):
        return len(self.sent_dict["word"])


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def cast_to_int(s):
    try:
        return int(s)
    except ValueError:
        return s


def word2id(sentences):
    """map words to word ids

    Args:
        sentences: a nested list of sentences

    """
    ids = defaultdict(lambda: len(ids))
    id_sents = [[ids[word] for word in sent] for sent in sentences]
    return id_sents, ids


# Compute log sum exp in a numerically stable way for the forward algorithm
def log_sum_exp(value, dim=None, keepdim=False):
    """Numerically stable implementation of the operation

    value.exp().sum(dim, keepdim).log()
    """
    if dim is not None:
        m, _ = torch.max(value, dim=dim, keepdim=True)
        value0 = value - m
        if keepdim is False:
            m = m.squeeze(dim)
        return m + torch.log(torch.sum(torch.exp(value0), dim=dim, keepdim=keepdim))
    else:
        m = torch.max(value)
        sum_exp = torch.sum(torch.exp(value - m))
        return m + torch.log(sum_exp)


def sents_to_vec(vec_dict, sentences):
    """read data, produce training data and labels.

    Args:
        vec_dict: a dict mapping words to vectors.
        sentences: A list of ConllSent objects

    Returns:
        embeddings: a list of tensors
        tags: a nested list of gold tags
    """
    embeddings = []
    for sent in sentences:
        sample = [vec_dict[word] for word in sent["word"]]
        embeddings.append(sample)

    return embeddings


def sents_to_tagid(sentences):
    """transform tagged sents to tagids,
    also return the look up table
    """
    ids = defaultdict(lambda: len(ids))
    id_sents = [[ids[tag] for tag in sent["tag"]] for sent in sentences]
    return id_sents, ids


def read_conll(fname, max_len=1e3, rm_null=True, prc_num=True):
    sentences = []
    sent = ConllSent()

    null_total = []
    null_sent = []
    loc = 0
    with open(fname) as fin:
        for line in fin:
            if line != '\n':
                line = line.strip().split('\t')
                sent["head"].append((int(line[0]),
                                     cast_to_int(line[3])))
                if rm_null and line[2] == '-NONE-':
                    null_sent.append(loc)
                else:
                    sent["tag"].append(line[2])
                    if prc_num and is_number(line[1]):
                        sent["word"].append('0')
                    else:
                        sent["word"].append(line[1])

                loc += 1
            else:
                loc = 0
                if len(sent) > 0 and len(sent) <= max_len:
                    sentences.append(sent)
                    null_total.append(null_sent)

                null_sent = []
                sent = ConllSent()

    return sentences, null_total


def write_conll(fname, sentences, pred_tags, null_total):
    with open(fname, 'w') as fout:
        for (pred, null_sent, sent) in zip(pred_tags, null_total, sentences):
            word_list = sent["word"]
            head_list = sent["head"]
            length = len(sent) + len(null_sent)
            assert (length == len(head_list))
            pred_tag_list = [str(k.item()) for k in pred]
            for null in null_sent:
                pred_tag_list.insert(null, '-NONE-')
                word_list.insert(null, '-NONE-')

            for i in range(length):
                fout.write("{}\t{}\t{}\t{}\n".format(
                    i + 1, word_list[i], pred_tag_list[i],
                    head_list[i][1]))
            fout.write('\n')


def input_transpose(sents, pad):
    max_len = max(len(s) for s in sents)
    batch_size = len(sents)

    sents_t = []
    masks = []
    for i in range(max_len):
        sents_t.append([sent[i] if len(sent) > i else pad for sent in sents])
        masks.append([1 if len(sent) > i else 0 for sent in sents])

    return sents_t, masks


def to_input_tensor(sents, pad, device):
    """
    return a tensor of shape (src_sent_len, batch_size)
    """

    sents, masks = input_transpose(sents, pad)

    sents_t = torch.tensor(sents, dtype=torch.float32, requires_grad=False, device=device)
    masks_t = torch.tensor(masks, dtype=torch.float32, requires_grad=False, device=device)

    return sents_t, masks_t


def data_iter(data, batch_size, is_test=False, shuffle=True):
    index_arr = np.arange(len(data))
    # in_place operation

    if shuffle:
        np.random.shuffle(index_arr)

    batch_num = int(np.ceil(len(data) / float(batch_size)))
    for i in range(batch_num):
        batch_ids = index_arr[i * batch_size: (i + 1) * batch_size]
        batch_data = [data[index] for index in batch_ids]

        if is_test:
            # batch_data.sort(key=lambda e: -len(e[0]))
            test_data = [data_tuple[0] for data_tuple in batch_data]
            tags = [data_tuple[1] for data_tuple in batch_data]

            yield test_data, tags

        else:
            # batch_data.sort(key=lambda e: -len(e))
            yield batch_data


def generate_seed(data, size, shuffle=True):
    index_arr = np.arange(len(data))
    # in_place operation

    if shuffle:
        np.random.shuffle(index_arr)

    seed = [data[index] for index in index_arr[:size]]

    return seed


def get_tag_set(tag_list):
    tag_set = set()
    tag_set.update([x for s in tag_list for x in s])
    return tag_set


def stable_math_log(val, default_val=-1e20):
    if val == 0:
        return default_val

    return math.log(val)


def unravel_index(input, size):
    """Unravel the index of tensor given size
    Args:
        input: LongTensor
        size: a tuple of integers

    Outputs: output,
        - **output**: the unraveled new tensor

    Examples::
        <<< value = torch.LongTensor(4,5,7,9)
        <<< max_val, flat_index = torch.max(value.view(4, 5, -1), dim=-1)
        <<< index = unravel_index(flat_index, (7, 9))
        <<< # output is a tensor with size (4, 5, 2)

    """
    idx = []
    for adim in size[::-1]:
        idx.append((input % adim).unsqueeze(dim=-1))
        input = input / adim
    idx = idx[::-1]
    return torch.cat(idx, -1)
