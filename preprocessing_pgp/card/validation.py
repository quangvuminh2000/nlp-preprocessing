import os
import re
from abc import ABC, abstractmethod

import pandas as pd
import numpy as np
import multiprocessing as mp
from tqdm import tqdm

from preprocessing_pgp.card.preprocess import (
    clean_card_data,
    extract_null_values
)
from preprocessing_pgp.card.utils import is_checker_valid
from preprocessing_pgp.utils import (
    sep_display,
    # apply_multi_process,
    apply_progress_bar
)
from preprocessing_pgp.card.const import (
    # Personal ID
    OLD_PID_CODE_LENGTH,
    NEW_PID_CODE_LENGTH,
    POSSIBLE_GENDER_NUM,
    OLD_PID_REGION_CODE_NUMS,
    NEW_PID_REGION_CODE_NUMS,
    # Passport
    PASSPORT_LENGTH,
    PASSPORT_PATTERN,
    # Driver License
    DRIVER_LICENSE_ID_REGION_CODES,
    INVALID_DRIVER_LICENSE_PASSING_YEAR,
    DRIVER_LICENSE_LENGTH,
    INVALID_DRIVER_LICENSE_FIRST_YEAR_CHAR,
    VALID_DRIVER_LICENSE_LAST_YEAR_CHAR
)

tqdm.pandas()
PROCESSES = os.cpu_count() // 2


class CardValidator(ABC):
    """
    Abstract Class contains validating functions for validating card_id
    """

    @staticmethod
    def is_valid_gender(gender_code: str) -> bool:
        """
        Check if the gender code is of correct format

        Parameters
        ----------
        gender_code : str
            Gender code extracted from card_id

        Returns
        -------
        bool
            Whether the gender code is at valid form
        """
        return gender_code in POSSIBLE_GENDER_NUM

    @staticmethod
    def is_all_digit_card(card_id: str) -> bool:
        """
        Check if the card_id contains all digit or not

        Parameters
        ----------
        card_id : str
            The card id

        Returns
        -------
        bool
            Whether the card id contains all digit or not
        """
        return card_id.isdecimal()

    @staticmethod
    @abstractmethod
    def is_valid_card(card_id: str) -> bool:
        """
        Check if the card is valid by syntax or not

        Parameters
        ----------
        card_id : str
            The input card id

        Returns
        -------
        bool
            Whether the card is valid by syntax
        """
        raise NotImplementedError("Subclasses should implement this!")


class PersonalIDValidator(CardValidator):
    """
    Class to check for personal id syntax
    """

    @staticmethod
    def is_old_card(card_id: str) -> bool:
        """
        Helper function to validate old card length
        """
        return len(card_id) == OLD_PID_CODE_LENGTH

    @staticmethod
    def is_new_card(card_id: str) -> bool:
        """
        Helper function to validate new card length
        """
        return len(card_id) == NEW_PID_CODE_LENGTH

    @staticmethod
    def is_valid_old_card(card_id: str) -> bool:
        """
        Helper function to check if the card_id is of old card type
        """
        if not PersonalIDValidator.is_old_card(card_id):
            return False
        return any((card in OLD_PID_REGION_CODE_NUMS
                    for card in [card_id[:2], card_id[:3]]))

    @staticmethod
    def is_valid_new_card(card_id: str) -> bool:
        """
        Helper function to check if the card_id is of old card type
        """
        if not PersonalIDValidator.is_new_card(card_id):
            return False

        if card_id[:3] in NEW_PID_REGION_CODE_NUMS:
            gender_code = card_id[3]
            return CardValidator.is_valid_gender(gender_code)

        return False

    @staticmethod
    def is_semi_correct_length(card_id: str) -> bool:
        """
        Helper function to check if the card_id length is still acceptable
        """
        return len(card_id) in (OLD_PID_CODE_LENGTH-1, NEW_PID_CODE_LENGTH-1)

    @staticmethod
    def is_valid_semi_card(card_id: str) -> bool:
        """
        Helper function to check if the card_id is of semi-correct length and is correct

        Steps
        -----

        1. Check the length of the card id
        2. Modify card id by adding '0' at the beginning and check for whether it is valid or not
        """
        if not PersonalIDValidator.is_semi_correct_length(card_id):
            return False

        modified_card_id = '0' + card_id
        return PersonalIDValidator.is_valid_old_card(modified_card_id)\
            or PersonalIDValidator.is_valid_new_card(modified_card_id)

    @staticmethod
    def is_valid_card(card_id: str) -> bool:
        """
        Check if the card is valid by personal id syntax or not

        Parameters
        ----------
        card_id : str
            The input card id

        Returns
        -------
        bool
            Whether the card is valid by personal id syntax
        """
        if not CardValidator.is_all_digit_card(card_id):
            return False

        return PersonalIDValidator.is_valid_new_card(card_id)\
            or PersonalIDValidator.is_valid_old_card(card_id)\
            or PersonalIDValidator.is_valid_semi_card(card_id)


class PassportValidator(CardValidator):
    """
    Class to check for passport id syntax
    """

    @staticmethod
    def is_valid_length(card_id: str) -> bool:
        """
        Helper function to validate the correct length of the card
        """
        return len(card_id) == PASSPORT_LENGTH

    @staticmethod
    def is_valid_syntax(card_id: str) -> bool:
        """
        Helper function to validate passport syntax:

        Steps
        -----

        1. Contains a starting character
        2. Next is 7 random digits
        """
        return bool(re.match(PASSPORT_PATTERN, card_id.lower()))

    @staticmethod
    def is_valid_card(card_id: str) -> bool:
        """
        Check if the card is valid by passport syntax or not

        Parameters
        ----------
        card_id : str
            The input card id

        Returns
        -------
        bool
            Whether the card is valid by passport syntax
        """
        return PassportValidator.is_valid_length(card_id)\
            and PassportValidator.is_valid_syntax(card_id)


class DriverLicenseValidator(CardValidator):
    """
    Class to check for driver license syntax
    """

    @staticmethod
    def is_valid_length(card_id: str) -> bool:
        """
        Helper function to validate the correct length of the card
        """
        return len(card_id) == DRIVER_LICENSE_LENGTH

    @staticmethod
    def is_valid_region_code(card_id: str) -> bool:
        """
        Function to check for valid region code in driver license card id
        """
        region_code = card_id[:2]

        return region_code in DRIVER_LICENSE_ID_REGION_CODES

    @staticmethod
    def is_valid_passing_year(card_id: str) -> bool:
        """
        Helper function to validate driver license passing year in card:
        """
        passing_year = card_id[3:5]

        return passing_year not in INVALID_DRIVER_LICENSE_PASSING_YEAR

    @staticmethod
    def is_valid_gender_code(card_id: str) -> bool:
        """
        Helper function to validate driver license passing year in card:
        """
        gender_code = card_id[2]

        return CardValidator.is_valid_gender(gender_code)

    @staticmethod
    def is_real_driver_license(card_id: str) -> bool:
        """
        Helper function to validate the card id
        in the case of the first 3 digits is in personal id region code
        """
        if PersonalIDValidator.is_valid_new_card(card_id):
            first_year_char = card_id[3]
            second_year_char = card_id[4]

            return (first_year_char not in
                    INVALID_DRIVER_LICENSE_FIRST_YEAR_CHAR)\
                and (second_year_char in
                     VALID_DRIVER_LICENSE_LAST_YEAR_CHAR)

        return True

    @staticmethod
    def is_valid_card(card_id: str) -> bool:
        """
        Check if the card is valid by driver license syntax or not

        Parameters
        ----------
        card_id : str
            The input card id

        Returns
        -------
        bool
            Whether the card is valid by passport syntax
        """
        if not CardValidator.is_all_digit_card(card_id):
            return False

        return DriverLicenseValidator.is_valid_length(card_id)\
            and DriverLicenseValidator.is_valid_region_code(card_id)\
            and DriverLicenseValidator.is_valid_gender_code(card_id)\
            and DriverLicenseValidator.is_valid_passing_year(card_id)\
            and DriverLicenseValidator.is_real_driver_license(card_id)


def verify_card(card_df: pd.DataFrame, card_col: str) -> pd.DataFrame:
    """
    Verify whether the card ids are valid or not

    Parameters
    ----------
    card_df : pd.DataFrame
        The input DF containing card id
    card_col : str
        The column contain card id

    Returns
    -------
    pd.DataFrame
        The final DF contains the columns that verify whether the card id is valid or not
    """
    orig_cols = card_df.columns.values.tolist()

    # ? CLEAN CARD ID
    sep_display()
    print(f"{'#'*5} CLEANSING CARD ID {'#'*5}")
    sep_display()

    # * Removing na values
    clean_card_df, na_card_df = extract_null_values(card_df, card_col)

    # * Basic cleaning card_id
    clean_card_df = clean_card_data(clean_card_df, card_col)

    print(f"# NAN CARD ID: {na_card_df.shape[0]}")
    sep_display()

    # ? VALIDATE CARD ID
    print(f"{'#'*5} VALIDATING CARD ID {'#'*5}")
    sep_display()

    print("Validating personal card id...")
    # * Check for valid personal card id
    clean_card_df['is_personal_id'] =\
        apply_progress_bar(
            PersonalIDValidator.is_valid_card,
            clean_card_df[card_col]
    )

    print(f"# PERSONAL ID FOUND: {clean_card_df['is_personal_id'].sum()}")
    sep_display()

    # * Check for valid passport id
    print("Validating passport id...")
    clean_card_df['is_passport'] =\
        apply_progress_bar(
            PassportValidator.is_valid_card,
            clean_card_df[card_col]
    )

    print(f"# PASSPORT FOUND: {clean_card_df['is_passport'].sum()}")
    sep_display()

    # * Check for valid driver license id
    print("Validating driver license id...")
    clean_card_df['is_driver_license'] =\
        apply_progress_bar(
            DriverLicenseValidator.is_valid_card,
            clean_card_df[card_col]
    )

    print(
        f"# DRIVER LICENSE FOUND: {clean_card_df['is_driver_license'].sum()}")
    sep_display()

    # * Make a general is_valid column to verify whether the card is generally valid

    clean_card_df['is_valid'] = clean_card_df.apply(
        lambda row: is_checker_valid(
            row['is_personal_id'],
            row['is_passport'],
            row['is_driver_license']
        ),
        axis=1
    )

    # ? CONCAT ALL SEP CARD IDS
    new_cols = ['is_valid', 'is_personal_id',
                'is_passport', 'is_driver_license']

    final_card_df = pd.concat([clean_card_df, na_card_df])

    final_card_df[new_cols] = final_card_df[new_cols].fillna(False)

    final_card_df = final_card_df[orig_cols + new_cols]

    return final_card_df
