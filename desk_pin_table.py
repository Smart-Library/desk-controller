from config.config import CONFIG
from desk import Desk
from sensors.omron_d6t.omron_d6t import OmronD6T


class DeskPinTable:
    """
    This class is responsible for mapping desk objects to GPIO pins, and registering pin events
    """

    # In this mapping, each entry is a tuple containing the desk id, the sensor object, and the respective desk object
    # The purpose of desk id in the tuple is used for easy lookup of desks
    # The sensor object is the object responsible for reading sensor data and reporting occupancy status
    # The desk object is used for performing additional operations on the desk if necessary
    __desk_mapping = []

    def __init__(self):
        """
        Initialize the DeskPinTable object. Register all pin event callbacks
        """
        self.__load_desk_dictionary()

    def __load_desk_dictionary(self):
        """
        Load the config file and initialize the desk mapping object
        :return: None
        """

        # Get all desks config
        all_desks = CONFIG.desks

        # Get info for each desk
        for d in all_desks:

            # Initialize sensor
            d_sensor = d.sensor
            sensor_obj = OmronD6T(d_sensor.i2c_bus, d_sensor.i2c_address)

            # Append id, pin, desk object to map
            self.__desk_mapping.append((d.id, sensor_obj, Desk(d.name, d.id)))

            # Print additional information in debug mode
            if CONFIG.debug_config.enabled:
                print("Added Desk to DeskPinTable: [ID]:", d.id, "[Name]:", d.name, "[Sensor Type]:", d.sensor.sensor_type)

    def poll_loop(self):
        """
        This method is used for polling each sensor for it's occupied status and updating the respective desk
        :return: None
        """
        for (desk_id, sensor_obj, desk_obj) in self.__desk_mapping:
            status = sensor_obj.occupied_status
            desk_obj.input_received(status)


    def get_mapping_from_desk_id(self, desk_id):
        """
        Lookup desk information given it's ID
        :param desk_id: The Desk ID to look for
        :return: A tuple containing the pin number and a Desk object if the ID corresponds to a Desk, or None
        """

        return next(((pin, d_obj) for d_id, pin, d_obj in self.__desk_mapping if d_id == desk_id), None)
