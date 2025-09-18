import json
import time

from wotreplay.helper.cleaners import Parser
from wotreplay.helper.extractor import Extractor
from wotreplay.utils.file_handler import FileHandler


class Replay:

    def __init__(self, file):
        self.start_time = time.time()
        self.file = str(file)
        self.short_name = Extractor.get_file_name(self.file)

        # Extract Data
        self._extract_data()
        self._assign_replay_date()
        self._assign_account_id()

    def _evaluate_replay(self):
        if len(self.battle_data) == 0:
            raise RuntimeError(f"{self.file} replay is not complete. "
                               f"Only the 'battle metadata' is available from incomplete replays")

    def _extract_data(self):
        """
        Extract data from one single replay.
        """

        # Open file
        file_object = FileHandler.open_file(self.file)

        # Clean the string file
        c = Parser(file_object)

        self.replay_data = c.replay_data

    def _assign_account_id(self):
        """
        Gets the account_id from the metadata
        """
        self.account_id = Extractor.get_account_id(self.replay_data)

    def _assign_replay_date(self):
        """
        Gets the replay_date from the metadata
        """
        self.replay_date = Extractor.get_replay_date(self.replay_data)

    def get_replay_fields(self):
        self.replay_fields = Extractor.extract_replay_fields(self.replay_data, self.short_name)

    def get_battle_metadata(self) -> list:
        """
        Extracts and loads
        """
        battle_metadata = Extractor.get_replay_metadata(data=self.replay_data, account_id=self.account_id,
                                                        replay_date=self.replay_date)

        return battle_metadata

    def get_battle_performance(self) -> list:
        """
        Extracts the battle performance data
        """
        self._evaluate_replay()
        performance = Extractor.get_battle_performance(data=self.replay_data, account_id=self.account_id,
                                                       replay_date=self.replay_date)
        return performance

    def get_common(self):
        self._evaluate_replay()
        common = Extractor.get_common(data=self.replay_data, account_id=self.account_id,
                                      replay_date=self.replay_date)
        return common

    def get_battle_frags(self):
        self._evaluate_replay()
        players = Extractor.get_battle_frags(data=self.replay_data, account_id=self.account_id,
                                             replay_date=self.replay_date)
        return players

    def get_battle_economy(self):
        self._evaluate_replay()
        economy = Extractor.get_battle_economy(data=self.replay_data, account_id=self.account_id,
                                               replay_date=self.replay_date)
        return economy

    def get_battle_xp(self):
        self._evaluate_replay()
        xp = Extractor.get_battle_xp(data=self.replay_data, account_id=self.account_id,
                                     replay_date=self.replay_date)
        return xp


if __name__ == "__main__":
    file = '../../files/20250825_1557_ussr-R174_BT-5_04_himmelsdorf.mtreplay'
    # file = '../../files/17580098444303_ussr_R40_T-54_ruinberg.wotreplay'

    r = Replay(file)

    r.get_replay_fields()

    replay_fields = r.replay_fields
    # print(f"replay_fields {replay_fields}")
    print(replay_fields.get('payload'))
    #
    # achievements_ids = Extractor.get_achievements(replay_fields.get('payload'))
    # print(f"achievements_ids {achievements_ids}")

    personal = Extractor.get_personal_by_player_id(replay_fields.get('payload'))
    print(f"personal {personal}")

    battle_frags = Extractor.get_battle_frags(replay_fields.get('payload'))
    print(f"battle_frags {battle_frags}")

    interactions = Extractor.get_player_interactions(replay_fields.get('payload'))
    print(f"interactions {interactions}")

    # meta_data = r.meta_data
    # print(f"meta_data = {meta_data}")
    #
    # replay_data = r.replay_data
    # print(f"replay_data = {replay_data}")
    #
    # battle_data = r.battle_data
    # print(f"battle_data {battle_data}")


    # data = {
    #     #'file_name': uploaded_file.name,
    #     #'payload': replay_data,
    #     # 'tank': tank,
    #     'battle_date': battle_metadata['dateTime'],
    #     'map_name': battle_metadata.get('mapName'),
    #     'map_display_name': battle_metadata.get('mapDisplayName'),
    #     # 'mastery': replay_data.get('mastery'),
    #     # 'credits': replay_data.get('credits', 0),
    #     # 'xp': replay_data.get('xp', 0),
    #     # 'kills': replay_data.get('kills', 0),
    #     # 'damage': replay_data.get('damage', 0),
    #     # 'assist': replay_data.get('assist', 0),
    #     # 'block': replay_data.get('block', 0)
    # }

    # print(data)