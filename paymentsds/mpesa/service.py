from .configuration import Configuration
from .exceptions import *
from .constants import *

import requests
from pprint import pprint

class Service:
  def __init__(self, **kwargs):
    self.config = Configuration(**kwargs)

  def handle_request(self, opcode, intent):
    data = self.fill_optional_properties(opcode, intent)

    missing_properties = self.detect_missing_properties(opcode, data)
    if len(missing_properties):
      raise MissingPropertyError()

    errors = self.detect_errors(opcode, data)
    if len(errors):
      raise ValidationError()

    return self.perform_request(opcode, data)

  def handle_send(self, data):
    opcode = self.detect_operation(data)
    if opcode:
        return self.handle_request(opcode, data)
    raise InvalidREceiverError()
    
  def handle_receive(self, data):
    return self.handle_request('C2B_PAYMENT', data)

  def handle_query(self, data):
    return self.handle_request('QUERY_TRANSACTION_STATUS', data)

  def handle_revert(self, data):
    return self.handle_request('REVERSAL', data)

  def detect_operation(self, data):
    if PATTERNS['PHONE_NUMBER'].match(data['to']):
      return 'B2C_PAYMENT'

    if PATTERNS['SERVICE_PROVIDER_CODE'].match(data['to']):
      return 'B2B_PAYMENT'

    return None

  def detect_errors(self, opcode, data):
    errors = []
    operation = DEFAULT_OPERATIONS[opcode]

    for k, v in data.items():
      regex = operation['validation'][k]
      if not regex.match(v):
        errors.append(k)

    return errors

  def detect_missing_properties(self, opcode, data):
    operation = DEFAULT_OPERATIONS[opcode]
    required_properties = set(operation['required'])
    given_properties = set(data.keys())
    missing_properties = required_properties - given_properties

    return list(missing_properties)

  def fill_optional_properties(self, opcode, data):
    def complete_to(to_complete):
      if 'to' not in to_complete.keys():
        if 'service_provider_code' in self.config.__dict__.keys():
          to_complete['to'] = self.config.service_provider_code

      return to_complete

    def complete_from(to_complete):
      if 'from' not in to_complete.keys():
        if 'service_provider_code' in self.config.__dict__.keys():
          to_complete['from'] = self.config.service_provider_code

      return to_complete

    def complete_reversal(to_complete):
      if 'to' not in to_complete.keys():
        if 'service_provider_code' in self.config.__dict__.keys():
          to_complete['to'] = self.config.service_provider_code

      if 'initiator_identifier' not in to_complete.keys():
        if 'initiator_identifier' in self.config.__dict__.keys():
          to_complete['initiator_identifier'] = self.config.initiator_identifier

      if 'security_credential' not in to_complete.keys():
        if 'security_credential' in self.config.__dict__.keys():
          to_complete['security_credential'] = self.config.security_credential

      return to_complete

    def complete_query_transaction_status(to_complete):
      if 'from' not in to_complete.keys():
        if 'service_provider_code' in self.config.__dict__.keys():
          to_complete['from'] = self.config.service_provider_code

      return to_complete

    if opcode == 'C2B_PAYMENT':
      return complete_to(data)
    elif opcode == 'B2B_PAYMENT':
      return complete_from(data)
    elif opcode == 'B2C_PAYMENT':
      return complete_from(data)
    elif opcode == 'REVERSAL':
      return complete_reversal(data)
    elif opcode == 'QUERY_TRANSACTION_STATUS':
      return complete_query_transaction_status(data)
    else:
      return data

  def perform_request(self, opcode, intent):
    self.generate_access_token()

    if hasattr(self.config, 'environment'):
      if hasattr(self.config, 'auth'):
        operation = DEFAULT_OPERATIONS[opcode]
        headers = self.build_request_headers()
        body = self.build_request_body(opcode, intent)

        request_data = {
          'base_url': '{}://{}'.format(self.config.environment.scheme, self.config.environment.domain),
          'path': operation['path'],
          'method': operation['method'],
          'headers': headers,
        }

        request_data['url'] = '{}:{}{}'.format(request_data['base_url'], operation['port'], operation['path'])

        response = None
        if operation['method'] == 'GET':
          request_data['params'] = body
          
          if self.config.timeout > 0:
            response = requests.get(request_data['url'], headers=headers, params=body, timeout=self.config.timeout)
          else:
            response = requests.get(request_data['url'], headers=headers, params=body)

        elif operation['method'] == 'PUT':
          request_data['data'] = body
        
          if self.config.timeout > 0:
            response = requests.put(request_data['url'], headers=headers, json=body, timeout=self.config.timeout)
          else:
            response = requests.put(request_data['url'], headers=headers, json=body)
        
        else:  
          request_data['data'] = body
          
          if self.config.timeout > 0:
            response = requests.post(request_data['url'], headers=headers, json=body, timeout=self.config.timeout)
          else:
            response = requests.post(request_data['url'], headers=headers, json=body)

        return response
      else:
        raise AuthenticationError()
    else:
      raise InvalidHostError()

  def generate_access_token(self):
    self.config.generate_access_token()

  def build_request_headers(self):
    return {
      'User-Agent': self.config.user_agent,
      'Origin': self.config.origin,
      'Authorization': 'Bearer {}'.format(self.config.auth)
    }

  def build_request_body(self, opcode, intent):
    body = {}

    for old_key, v in intent.items():
      new_key = DEFAULT_OPERATIONS[opcode]['mapping'][old_key]
      if (opcode == 'C2B_PAYMENT' and old_key == 'from') or (opcode == 'B2C_PAYMENT' and old_key == 'to'):
        body[new_key] = self.normalize_phone_number(intent[old_key])
      else:
        body[new_key] = intent[old_key]
    
    return body

  def normalize_phone_number(self, str):
    return str