import os

import requests
import time
import json
import dpath.util

import utils


class Compute:

    def __init__(self,
                 host_node,
                 port=8491,
                 log=False):

        """ If remote_node is unspecified, then assumes use of a local Compute node """

        self.log = log
        self.port = port
        self.host_node = host_node

    def remote(self):
        return self.host_node.remote()

    def base_url(self):
        return utils.getbaseurl(self.host_node.host, self.port)

    def get_entity_config(self, entity_name):
        param_dic = {'entity': entity_name}
        r = requests.get(self.base_url() + '/config', params=param_dic)

        if self.log:
            print "LOG: Get config: /config with params " + json.dumps(param_dic) + ", response = ", r
            print "  LOG: response text = ", r.text
            print "  LOG: url: ", r.url

        config = r.json()
        return config

    def wait_till_param(self, entity_name, param_path, value, max_tries=-1):
        """
        Return when the the config parameter has achieved the value specified
        entity = name of entity, param_path = path to parameter, delimited by '.'
        
        If there are too many connection errors, exit the whole program.
        """

        max_connection_error = 20

        wait_period = 10
        age = None
        i = 0
        connection_error_count = 0

        print "... Waiting for param to achieve value (try every " + str(wait_period) + "s): " + entity_name + \
              "." + param_path + " = " + str(value)

        def print_age(i, age_string):
            # if not self.log:
            #     utils.restart_line()
            print "Try = [%d]%s" % (i, age_string)  # add a comma at the end to remove newline

        while True:
            i += 1

            age_string = ""
            if age is not None:
                age_string = ", " + entity_name + ".age = " + str(age)

            if 0 < max_tries < i:
                print_age(i, age_string)
                msg = "ERROR: Tried " + str(max_tries) + " times, without success, AGIEF is considered hung."
                raise Exception(msg)

            if connection_error_count > max_connection_error:
                msg = "ERROR: too many connection errors: " + str(max_connection_error)
                raise Exception(msg)

            if i % 5 == 0:
                print_age(i, age_string)

            try:
                config = self.get_entity_config(entity_name)

                if 'value' in config:
                    age = dpath.util.get(config, 'value.age', '.')
                    parameter = dpath.util.get(config, 'value.' + param_path, '.')
                    if parameter == value:
                        if self.log:
                            print "LOG: ... parameter: " + entity_name + "." + param_path + ", has achieved value: " + \
                                  str(value) + "."
                        break
            except KeyError:
                print "KeyError Exception"
                print "WARNING: trying to access a keypath in config object, that DOES NOT exist!"
            except requests.exceptions.ConnectionError:
                print "Oops, ConnectionError exception"
                connection_error_count += 1
            except requests.exceptions.RequestException:
                print "Oops, request exception"

            time.sleep(wait_period)  # sleep for n seconds

        # successfully reached value
        print_age(i, age_string)
        print "   -> success, parameter reached value" + age_string

    def import_experiment(self, entity_filepath=None, data_filepaths=None):
        """setup the running instance of AGIEF with the input files"""

        is_entity_file = entity_filepath is not None
        is_data_files = data_filepaths is not None or len(data_filepaths) != 0

        print "\n....... Import Experiment"

        if not is_entity_file and not is_data_files:
            print "        WARNING: no input files specified (that may be intentional)"
            return

        print "     Input files: "
        if is_entity_file:
            print "        Entities:" + entity_filepath
        if is_data_files:
            print "        Data: " + json.dumps(data_filepaths)

        if is_entity_file:
            if not os.path.isfile(entity_filepath):
                raise Exception("ERROR: entity file does not exist.")

            with open(entity_filepath, 'rb') as entity_data_file:
                files = {'entity-file': entity_data_file}
                response = requests.post(self.base_url() + '/import', files=files)
                if self.log:
                    print "LOG: Import entity file, response = ", response
                    print "  LOG: response text = ", response.text
                    print "  LOG: url: ", response.url
                    print "  LOG: post body = ", files

        if is_data_files:
            for data_filepath in data_filepaths:
                if not os.path.isfile(data_filepath):
                    raise Exception("ERROR: data file does not exist.")

                with open(data_filepath, 'rb') as data_data_file:
                    files = {'data-file': data_data_file}
                    response = requests.post(self.base_url() + '/import', files=files)
                    if self.log:
                        print "LOG: Import data file, response = ", response
                        print "  LOG: response text = ", response.text
                        print "  LOG: url: ", response.url
                        print "  LOG: post body = ", files

    def import_compute_experiment(self, filepaths, is_data):
        """
        Load data files into AGIEF compute node,
        by requesting it to load a local file (i.e. file on the compute machine)

        :param filepaths: full path to file on compute node
        :param is_data: if true, then load 'data', otherwise load 'entity'
        :return:
        """

        print "\n....... Import Data on Compute node into Experiment "

        import_type = 'entity'
        if is_data:
            import_type = 'data'

        is_data_files = filepaths is not None or len(filepaths) != 0

        if is_data_files:
            print "     Input files: "
            print "      Data: " + json.dumps(filepaths)
        else:
            print "      No files to import"
            return

        for filepath in filepaths:
            payload = {'type': import_type, 'file': filepath}
            response = requests.get(self.base_url() + '/import-local', params=payload)

            if self.log:
                print "LOG: Import data file, response = ", response
                print "  LOG: response text = ", response.text
                print "  LOG: url: ", response.url

    def run_experiment(self, exp):

        print "\n....... Run Experiment"

        payload = {'entity': exp.entity_with_prefix('experiment'), 'event': 'update'}
        response = requests.get(self.base_url() + '/update', params=payload)
        if self.log:
            print "LOG: Start experiment, response = ", response

        # wait for the task to finish (poll API for 'Terminated' config param)
        self.wait_till_param(exp.entity_with_prefix('experiment'), 'terminated', True)

    def export_root_entity(self, filepath, root_entity, export_type, is_compute_save=False):
        """
        Export the subtree specified by root entity - either we save locally,
        or specify the Compute node to save it itself
        :param filepath: if specified, then receive a string
        :param root_entity:
        :param export_type:
        :param is_compute_save: boolean, if false (default) then returned as string and then we save the file
        if true then 'Compute' saves the file, using the path to a folder (for the compute machine) specified by filepath
        :return:
        """

        if not is_compute_save:
            payload = {'entity': root_entity, 'type': export_type}
        else:
            payload = {'entity': root_entity, 'type': export_type, "export-location": filepath}

        response = requests.get(self.base_url() + '/export', params=payload)

        if is_compute_save:
            print "Saved file response: ", response.text

        if self.log:
            # print "Exported entity file, response text = ", response.text
            print "  LOG: response = ", response
            print "  LOG: response url = ", response.url

        if not is_compute_save:
            # write back to file
            output_json = response.json()
            utils.create_folder(filepath)
            with open(filepath, 'w') as data_file:
                data_file.write(json.dumps(output_json, indent=4))

    def export_subtree(self, root_entity, entity_filepath, data_filepath, is_export_compute=False):
        """
        Export the full state of a subtree from the running instance of AGIEF
        that consists of entity graph and the data
        """

        print "\n....... Export Experiment"
        if self.log:
            print "Exporting data for root entity: " + root_entity

        self.export_root_entity(entity_filepath, root_entity, 'entity', is_export_compute)
        self.export_root_entity(data_filepath, root_entity, 'data', is_export_compute)

    def wait_up(self):
        wait_period = 3

        print "\n....... Wait till framework has started (try every " + str(wait_period) + " seconds),   at = " \
              + self.base_url()

        i = 0
        while True:
            i += 1
            if i > 120:
                raise Exception("Error: could not start framework.")

            version = self.version(True)

            if version is None:
                # utils.restart_line()
                print "Try = [%d / 120]" % i  # add comma at the end to remove newline
                time.sleep(wait_period)
            else:
                break

        print "\n  - framework is up, running version: " + version

    def terminate(self):
        print "\n...... Terminate framework"
        response = requests.get(self.base_url() + '/stop')

        if self.log:
            print "LOG: response text = ", response.text

    def set_parameter_db(self, entity_name, param_path, value):
        """
        Set parameter at 'param_path' for entity 'entity_name', in the DB
        'entity_name' is the fully qualified name WITH the prefix
        """

        payload = {'entity': entity_name, 'path': param_path, 'value': value}
        response = requests.post(self.base_url() + '/config', params=payload)
        if self.log:
            print "LOG: set_parameter_db: entity_name = " + entity_name + ", param_path = " + param_path + ", value = "\
                  + value
            print "LOG: response = ", response

    @staticmethod
    def set_parameter_inputfile(entity_filepath, entity_name, param_path, value):
        """
        Set parameter at 'param_path' for entity 'entity_name', in the input file specified by 'entity_filepath'

        :param entity_filepath: modify values in this file (full path)
        :param entity_name: the fully qualified entity name, WITH Prefix
        :param param_path: set parameter at this path
        :param value:
        :return:
        """

        log_debug = False

        set_param = entity_name + "." + param_path + " = " + str(value)

        if log_debug:
            print "LOG: in file: " + entity_filepath

        # open the entity input file
        with open(entity_filepath) as data_file:
            data = json.load(data_file)

        # get the first element in the array with dictionary field "entity-name" = entity_name
        entity = dict()
        for entity_i in data:
            if not entity_i["name"] == entity_name:
                continue
            entity = entity_i
            break

        if not entity:
            msg = "\nERROR: Could not find an entity in the input file matching the entity name specified in the " \
                  "experiment file in field 'file-entities'.\n"
            msg += "\tEntity input file: " + entity_filepath + "\n"
            msg += "\tEntity name: " + entity_name
            raise Exception(msg)

        config = utils.get_entityfile_config(entity, log_debug)

        if log_debug:
            print "LOG: config(t)   = " + json.dumps(config, indent=4)

        changed = dpath.util.set(config, param_path, value, '.')

        if changed == 0:
            msg = "\nERROR: Could not set the config in entity at param path.\n"
            msg += "\tEntity = " + entity_name + "\n"
            msg += "\tParam_path = " + param_path
            raise Exception(msg)

        if log_debug:
            print "LOG: config(t+1) = " + json.dumps(config, indent=4)

        utils.set_entityfile_config(entity, config, log_debug)

        # write back to file
        with open(entity_filepath, 'w') as data_file:
            data_file.write(json.dumps(data, indent=4))

        return set_param

    def version(self, is_suppress_console_output=False):
        """
        Find out the version from the running framework, through the RESTful API. Return the string,
        or None if it could not retrieve the version.
        """

        version = None
        try:
            response = requests.get(self.base_url() + '/version')
            if self.log:
                print "LOG: response = ", response

            response_json = response.json()
            if 'version' in response_json:
                version = response_json['version']

        except requests.ConnectionError:
            version = None

            if not is_suppress_console_output:
                print "Error connecting to agief to retrieve the version."

        return version