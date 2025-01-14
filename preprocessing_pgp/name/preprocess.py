import string
import re
import os
import sys
from string import punctuation
from typing import Tuple

import pandas as pd
from tqdm import tqdm
from halo import Halo

from preprocessing_pgp.accent_typing_formatter import reformat_vi_sentence_accent
from preprocessing_pgp.name.unicode_converter import minimal_convert_unicode
from preprocessing_pgp.name.extract_human import replace_non_human_reg

_dir = "/".join(os.path.split(os.getcwd()))
if _dir not in sys.path:
    sys.path.append(_dir)


def remove_special_chars(sentence: str) -> str:
    """
    Removing special characters from sentence

    Parameters
    ----------
    sentence : str
        The input sentence can contains many special characters and alpha characters

    Returns
    -------
    str
        The sentence contains only alpha characters
    """
    return sentence.translate(str.maketrans('', '', punctuation))


def remove_spare_spaces(sentence: str) -> str:
    """
    Removing spare spaces inside a sentence

    Parameters
    ----------
    sentence : str
        Sentence to clean spare spaces

    Returns
    -------
    str
        Cleaned sentence
    """

    # Remove spaces in between
    sentence = re.sub(' +', ' ', sentence)
    # Remove additional leading & trailing spaces
    sentence = sentence.strip()

    return sentence


def format_caps_word(sentence: str) -> str:
    """
    Format the sentence into capital format

    Parameters
    ----------
    sentence : str
        The input sentences

    Returns
    -------
    str
        Capitalized sentence of the input sentence
    """
    caps_sen = sentence.lower()
    caps_sen = string.capwords(caps_sen)

    return caps_sen


def basic_preprocess_name(name: str) -> str:
    """
    Preprocess names based on these steps:

        1. Remove spare spaces
        2. Format name into capitalized
        3. Change name to Unicode compressed format
        4. Change name to same old accent typing format
        5. Re-capitalized the word

    Parameters
    ----------
    name : str
        The input raw name

    Returns
    -------
    str
        The preprocessed name
    """
    # Remove Spare Spaces
    clean_name = remove_spare_spaces(name)

    # Remove Special Characters
    clean_name = remove_special_chars(clean_name)

    # Format Caps
    caps_name = format_caps_word(clean_name)

    # Change to same VN charset -> Unicode compressed
    unicode_clean_name = minimal_convert_unicode(caps_name)

    # Change to same accent typing -> old type
    old_unicode_clean_name = reformat_vi_sentence_accent(unicode_clean_name)

    old_unicode_clean_name = format_caps_word(old_unicode_clean_name)

    return old_unicode_clean_name


def clean_name_cdp(name: str) -> str:
    """
    Specific function to clean name from customer profile

    Parameters
    ----------
    name : str
        The name of the customer

    Returns
    -------
    str
        The clean name of the customer
    """
    if name is None:
        return None
    clean_name = basic_preprocess_name(name)
    clean_name = replace_non_human_reg(name)
    return clean_name


@Halo(
    text='Preprocessing Names',
    color='cyan',
    spinner='dots7',
    text_color='magenta'
)
def preprocess_df(
    data: pd.DataFrame,
    # human_extractor: HumanNameExtractor,
    name_col: str = 'name',
    # extract_human: bool = False,
    # multiprocessing: bool = False,
    # n_cpu: int = None
) -> pd.DataFrame:
    """
    Perform basic preprocessing to names in the input data

    Parameters
    ----------
    df : pd.DataFrame
        The input data containing the columns with name records
    name_col : str, optional
        The column contains the name records, by default 'name'

    Returns
    -------
    pd.DataFrame
        The finalized data with clean names
    """
    basic_clean_names = data.copy()
    basic_clean_names[f'clean_{name_col}'] = basic_clean_names[name_col].apply(
        basic_preprocess_name)

    basic_clean_names = basic_clean_names.drop(columns=[name_col])
    basic_clean_names = basic_clean_names.rename(columns={
        f'clean_{name_col}': name_col
    })

    return basic_clean_names
