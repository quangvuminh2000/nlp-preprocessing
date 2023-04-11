import string
import re
from string import punctuation

import pandas as pd
from unidecode import unidecode

from preprocessing_pgp.accent_typing_formatter import reformat_vi_sentence_accent
from preprocessing_pgp.name.unicode_converter import minimal_convert_unicode
from preprocessing_pgp.name.extract_human import replace_non_human_reg
from preprocessing_pgp.name.utils import remove_nicknames
from preprocessing_pgp.name.const import (
    PRONOUN_REGEX,
    WITHOUT_ACCENT_ELEMENTS,
    WITH_ACCENT_ELEMENTS
)


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


def remove_non_word(sentence: str) -> str:
    """
    Removing all non-word character from sentence

    Parameters
    ----------
    sentence : str
        The input sentence can contains symbols, special non-utf8 characters

    Returns
    -------
    str
        The sentence not contain any special character
    """
    clean_sentence = re.sub(r'[^\w]', ' ', sentence)
    return clean_sentence


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


def remove_non_characters(name: str) -> str:
    """
    Remove non-utf8 characters from string
    """
    clean_name = re.sub(r'(?i)[^\u0030-\u0039\u0061-\u007A\u00C0-\u1EF8 ]', '', name)
    clean_name = re.sub(r'\d+', '', clean_name)
    return clean_name


def remove_special_cases(name: str) -> str:
    """
    Remove some special cases
    """
    clean_name = re.sub(r'(?i)\(.*\)', ' ', name)
    clean_name = re.sub(r'(?i)\[.*\]', ' ', clean_name)

    return clean_name.strip()


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

    # Remove special cases
    clean_name = remove_special_cases(name)

    # Remove all non-word characters
    clean_name = remove_non_characters(clean_name)

    # Remove Spare Spaces
    clean_name = remove_spare_spaces(clean_name)

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


def get_name_pronoun(name: str) -> str:
    """
    Function to get pronoun from name

    Parameters
    ----------
    name : str
        The name input

    Returns
    -------
    str
        The output pronoun found if any
    """
    try:
        processed_name = name.lower().strip()
        pronouns = re.findall(PRONOUN_REGEX, processed_name)
        pronoun = pronouns[0].strip()
    except:
        pronoun = None

    return pronoun


def remove_pronoun_from_name(name: str) -> str:
    """
    Remove pronoun from name
    """
    processed_name = name.lower().strip()
    processed_name = re.sub(PRONOUN_REGEX, ' ', processed_name)
    return processed_name


def remove_invalid_base_element(name: str) -> str:
    """
    Remove non vietnamese name base part in raw

    Parameters
    ----------
    name : str
        Non-Vietnamese name

    Returns
    -------
    str
        The cleansed name without non-vietnamese
    """

    if name is None:
        return None

    return ' '.join(
        part for part in name.lower().split(' ')
        if unidecode(part) in WITHOUT_ACCENT_ELEMENTS
    ).title()


def remove_invalid_element(name: str) -> str:
    """
    Remove non vietnamese name element in raw

    Parameters
    ----------
    name : str
        Non-Vietnamese name

    Returns
    -------
    str
        The cleansed name without non-vietnamese
    """
    if name is None:
        return None

    return ' '.join(
        part for part in name.lower().split(' ')
        if part in WITH_ACCENT_ELEMENTS
    ).title()


def preprocess_df(
    data: pd.DataFrame,
    # human_extractor: HumanNameExtractor,
    name_col: str = 'name',
    clean_name: bool = True,
    remove_pronoun: bool = True
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
    clean_name : bool, optional
        Whether to clean the name separated by space, by default True

    Returns
    -------
    pd.DataFrame
        The finalized data with clean names
    """
    # * Filter out columns
    other_cols = data.columns.difference([name_col])

    # * Na names & filter out name col
    na_data = data[data[name_col].isna()][[name_col]]
    cleaned_data = data[data[name_col].notna()][[name_col]]

    # * Cleansing data
    cleaned_data[f'clean_{name_col}'] =\
        cleaned_data[name_col].apply(
            basic_preprocess_name
        )

    # * Remove nickname
    cleaned_data = remove_nicknames(
        cleaned_data,
        f'clean_{name_col}'
    )

    # * Remove name pronoun
    if remove_pronoun:
        cleaned_data[f'clean_{name_col}'] =\
            cleaned_data[name_col].apply(
                remove_pronoun_from_name
            )

    # * Extra cleansing name
    if clean_name:
        cleaned_data[f'clean_{name_col}'] =\
            cleaned_data[f'clean_{name_col}'].apply(
                remove_invalid_base_element
        )

    cleaned_data = cleaned_data.drop(columns=[name_col])
    cleaned_data = cleaned_data.rename(columns={
        f'clean_{name_col}': name_col
    })

    # * Concat na data
    final_data = pd.concat([
        cleaned_data,
        na_data
    ])

    # * Concat with original cols
    new_cols = [
        name_col
    ]
    final_data = pd.concat([
        data[other_cols],
        final_data[new_cols]
    ], axis=1)

    return final_data
