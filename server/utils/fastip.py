import bz2
import os
import struct
import ipaddress
import json

class FastIPDatabaseEntry:
    def __init__(self, country_en, country_code):
        self.country_en = country_en
        self.country_code = country_code

def _read_u32(stream):
    return struct.unpack('<I', stream.read(4))[0]

def _read_u16(stream):
    return struct.unpack('<H', stream.read(2))[0]

def _json_get_or(json_value, key, value=None):
    return json_value[key] if key in json_value else value

def _read_entry(stream):
    entry_size = _read_u16(stream)
    try:
        json_str = stream.read(entry_size).decode('utf-8')
        json_value = json.loads(json_str)
        country_en = _json_get_or(json_value, 'country_en')
        country_code = _json_get_or(json_value, 'country_code')
        return FastIPDatabaseEntry(country_en, country_code)
    except:
        return FastIPDatabaseEntry(None, None)

class FastIPDatabase:
    def __init__(self, filename):
        with bz2.BZ2File(filename, 'rb') as f:
            self.num_prefix_to_record_entries = 0x10000

            self.num_records = _read_u32(f)
            self.num_entries = _read_u32(f)
            self.prefix_to_record_start = [0] * self.num_prefix_to_record_entries
            self.prefix_to_record_end = [0] * self.num_prefix_to_record_entries
            self.prefix_to_suffix = [0] * self.num_records
            self.record_to_entry_idx = [0] * self.num_records
            self.entries = [None] * self.num_entries

            for i in range(self.num_prefix_to_record_entries):
                start_idx = _read_u32(f)
                end_idx = _read_u32(f)
                if start_idx > end_idx:
                    raise Exception('Invalid fastip file. start_idx > end_idx.')
                if end_idx > self.num_records:
                    raise Exception('Invalid fastip file. end_idx > num_records.')
                self.prefix_to_record_start[i] = start_idx
                self.prefix_to_record_end[i] = end_idx

            for i in range(self.num_records):
                self.prefix_to_suffix[i] = _read_u16(f)
                self.record_to_entry_idx[i] = _read_u32(f)
                if self.record_to_entry_idx[i] >= self.num_entries:
                    raise Exception('Invalid fastip file. entry_idx >= num_entries.')

            for i in range(self.num_entries):
                self.entries[i] = _read_entry(f)

    def query_by_ip(self, ip):
        ip_bytes = ipaddress.IPv4Address(ip).packed
        ip_int = int.from_bytes(ip_bytes, 'big')
        prefix_lookup_idx = ip_int >> 16
        cur_idx = self.prefix_to_record_start[prefix_lookup_idx];
        end_idx = self.prefix_to_record_end[prefix_lookup_idx];
        while cur_idx <= end_idx:
            if cur_idx == end_idx:
                break
            next_idx = (cur_idx + end_idx) // 2
            cur_suffix = self.prefix_to_suffix[next_idx]
            if cur_suffix == (ip_int & 0xFFFF):
                break
            if cur_suffix <= (ip_int & 0xFFFF):
                cur_idx = next_idx + 1
            else:
                end_idx = next_idx
        return self.entries[self.record_to_entry_idx[cur_idx]]

script_dir = os.path.dirname(os.path.abspath(__file__))
default_fastip_database_path = os.path.join(script_dir, 'fastip.bin.bz2')
default_fastip_database = FastIPDatabase(default_fastip_database_path)

def query_by_ip(ip_str):
    return default_fastip_database.query_by_ip(ip_str)
