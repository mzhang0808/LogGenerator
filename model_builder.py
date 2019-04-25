from activity import Activity, Gateway, Transition, Process
from resource import HumanResource, PhysicalResource
from data_object import Form
from xml.etree import ElementTree
from collections import OrderedDict
from copy import deepcopy


class ModelBuilder:

    def __init__(self):
        self.activities = dict()
        activity_list = self.create_activities()
        for act in activity_list:
            self.activities[act.id] = act

    def create_activities(self):
        # TODO: Add the file locations to some configuration that the model builder accesses
        return self._create_from_file('activities.xml', 'Activity', self._parse_activity)

    def create_resources(self):
        # TODO: Add the file locations to some configuration that the model builder accesses
        return self._create_from_file('resources.xml', 'Resource', self._parse_resource)

    def create_data(self):
        # TODO: Add the file locations to some configuration that the model builder accesses
        return self._create_from_file('data.xml', 'DataObject', self._parse_data)

    def create_process_model(self):
        # TODO: Add the file locations to some configuration that the model builder accesses
        return self._create_from_file('models.xml', 'Model', self._parse_process_model)

    def _create_from_file(self, file_name, tag_name, parser):
        container = []
        root = ElementTree.parse(file_name).getroot()
        for child in root:
            if child.tag == tag_name:
                container.append(parser(child))
        return container

    def _parse_activity(self, activity_child):
        activity_fields = self._parse_activity_fields(activity_child)

        return Activity(id=activity_fields.get('id'), name=activity_fields.get('name'), distribution=activity_fields.get('distribution', 0), data_input=activity_fields.get('data_input'), data_output=activity_fields.get('data_output'), resources=activity_fields.get('resources'), failure_rate=activity_fields.get('failure_rate', 0), retries=activity_fields.get('retries', 0), timeout=activity_fields.get('timeout'), priority=activity_fields.get('priority', 'normal'))

    def _parse_activity_fields(self, activity_child):
        fields = dict()
        fields['id'] = activity_child.get('id')

        try:
            fields['name'] = activity_child.find('Name').text
        except AttributeError:
            pass

        fields['distribution'] = self._parse_distribution(activity_child.find('Duration/Distribution'))

        data_input = []
        data_input_child = activity_child.find('DataInput')
        # TODO: Add some checking to verify that the children objects are what we think they are.
        if data_input_child is not None:
            for data_object in data_input_child:
                data = dict()
                id = data_object.get('id')
                if id is None:
                    # TODO: better way to handle custom exception
                    raise AttributeError('Missing data object id.')
                data['id'] = id
                if data_object.get('type') == 'form':
                    fields_child = data_object.find('Fields')
                    if fields_child is not None:
                        data['fields'] = dict()
                        for field in fields_child:
                            data['fields'][field.get('name')] = field.text
                data_input.append(data)

        fields['data_input'] = data_input

        data_output = []
        data_output_child = activity_child.find('DataOutput')

        if data_output_child is not None:
            for data_object in data_output_child:
                data = dict()
                id = data_object.get('id')
                if id is None:
                    # TODO: better way to handle custom exception
                    raise AttributeError('Missing data object id.')
                data['id'] = id
                if data_object.get('type') == 'form':
                    fields_child = data_object.find('Fields')
                    if fields_child is not None:
                        data['fields'] = dict()
                        for field in fields_child:
                            data['fields'][field.get('name')] = field.text
                data_output.append(data)
        fields['data_output'] = data_output

        resources = []
        resources_child = activity_child.find('Resources')

        if resources_child is not None:
            for resource in resources_child:
                # TODO: Change resources to be more flexible. We need to accept subtypes of resources and etc. For now we specify one type of resource.
                try:
                    res = resource.attrib
                    res['qty'] = resource.text
                    resources.append(res)
                except AttributeError:
                    print('Poorly formatted resource')
        fields['resource'] = resources
        failure_rate = None
        retries = None
        failure_child = activity_child.find('FailureRate')

        if failure_child is not None:
            failure_rate = failure_child.text
            retries = failure_child.get('retries')
        fields['failure_rate'] = failure_rate
        fields['retries'] = retries

        # TODO: implement similar try/except methodology for others.
        try:
            timeout = activity_child.find('Timeout').text
        except AttributeError:
            timeout = None
        fields['timeout'] = timeout

        try:
            priority = activity_child.find('Priority').text
        except AttributeError:
            priority = None
        fields['priority'] = priority

        return fields

    def _parse_resource(self, resource_child):
        class_type = resource_child.get('type')
        id = resource_child.get('id')
        qty = resource_child.find('Quantity').text

        if class_type == 'human':
            org = resource_child.find('Organization').text
            dept = resource_child.find('Department').text
            role = resource_child.find('Role').text
            availability = self._parse_calendar(resource_child.find('Availability'))
            res = HumanResource(id, org, dept, role, availability)
        elif class_type == 'physical':
            type = resource_child.find('Type').text
            delay = self._parse_distribution(resource_child.find('Delay/Distribution'))
            res = PhysicalResource(id, type, qty, delay)
        else:
            raise AttributeError('Poorly formatted resource.')
        return res

    @classmethod
    def _parse_distribution(cls, distribution_child):
        if distribution_child is None:
            return None
        try:
            return distribution_child.attrib
            # TODO: Think of case when the duration is fixed and not a distribution.
        except AttributeError:
            print('Poorly formatted duration.')

    @classmethod
    def _parse_calendar(cls, availability_child):
        calendar = {}
        for day in availability_child:
            for block in day:
                for time in range(int(block.get('start')), int(block.get('end'))):
                    calendar.setdefault(day.tag, {})
                    calendar[day.tag][time] = True if block.text is None else block.text
        return calendar

    def _parse_process_model(self, model_child):
        id = model_child.get('id')
        name = model_child.find('Name').text
        arrival_rate = self._parse_calendar(model_child.find('ArrivalRate'))
        deadline = model_child.find('Deadline').text
        gateways = []
        for gateway in model_child.find('Gateways'):
            gateways.append(self._parse_gateway(gateway))
        transitions = []
        activities = dict()
        resources = dict()
        data_objects = dict()
        for transition in model_child.find('Transitions'):
            transition_object = self._parse_transition(transition)
            transitions.append(transition_object)
            # parse activity from transitions
            if transition_object.source not in activities:
                source = self._clone_activity(transition_object.source)
                if source is not None:
                    activities[source.id] = source
                    resources, data_objects = self._parse_from_existing(source, resources, data_objects)
            if transition_object.destination not in activities:
                destination = self._clone_activity(transition_object.destination)
                if destination is not None:
                    activities[destination.id] = destination
                    resources, data_objects = self._parse_from_existing(destination, resources, data_objects)
        for act in model_child.find('Activities'):
            # TODO: check if this works
            fields = self._parse_activity_fields(act)
            activities[fields['id']].update(fields)
        return Process(id=id, name=name, arrival_rate=arrival_rate, deadline=deadline, activities=activities, gateways=gateways, transitions=transitions, data_objects=list(data_objects.values()), resources=list(resources.values()))

    @classmethod
    def _parse_from_existing(cls, item, resources, data_objects):
        for resource in (item.resources or []):
            resources[resource.id] = resource
        for data_object in (item.data_input or []):
            data_objects[data_object.id] = data_object
        for data_object in (item.data_output or []):
            data_objects[data_object.id] = data_object
        return resources, data_objects

    @classmethod
    def _parse_gateway(cls, gateway_child):
        id = gateway_child.get('id')
        name = gateway_child.find('Name').text
        type = gateway_child.find('Type').text.lower()
        # TODO: transform all these type names in enums so they can be easily modified at one place
        gates = []
        distribution = None
        rule = None
        if type == 'choice':
            distribution_child = gateway_child.find('Distribution')
            rule_child = gateway_child.find('Rule')
            if distribution_child is not None and len(list(distribution_child)):
                distribution = []
                for gate in distribution_child:
                    gates.append(gate.get('id'))
                    distribution.append(gate.text)
            elif rule_child is not None and len(list(rule_child)):
                # TODO: Parse rule based gateway
                # TODO: Don't forget to extract gates from here.
                gates = []
                rule = None
            else:
                raise ValueError("For choice gateways, either rule or distribution must be present.")
        return Gateway(id=id, name=name, type=type, gates=gates, distribution=distribution, rule=rule)

    def _parse_transition(self, transition_child):
        source = transition_child.get('source')
        destination = transition_child.get('destination')
        gate = transition_child.get('gate')
        distribution_child = transition_child.find('Duration/Distribution')
        if distribution_child is not None:
            distribution = self._parse_distribution(distribution_child)
        else:
            distribution = 0

        return Transition(source=source, destination=destination, gate=gate, distribution=distribution)

    def _parse_data(self, data_child):
        id = data_child.get('id')
        type = data_child.get('type')

        if type == 'form':
            name, fields = self._parse_form(data_child)
            return Form(id, name, fields)
        else:
            raise ValueError('Data type not supported.')

    @classmethod
    def _parse_form(cls, form_child):
        # TODO: This is the model going forward. Do NO verification on format and do xml validation on initialization.
        name = form_child.find('Name').text
        fields = OrderedDict()
        for field in form_child.find('Fields'):
            fields[field.get('name')] = field.text
        return name, fields

    def _clone_activity(self, id):
        if id not in self.activities:
            return None
        else:
            return deepcopy(self.activities[id])
        pass

























