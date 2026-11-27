"""Verify installed bytes, import isolation and schema from the built artifact."""
import argparse
import hashlib
import importlib
from importlib.util import find_spec
import json
from pathlib import Path
import pkgutil
import zipfile

import gabfin
from gabfin.contracts.schema import generate_schema


def run(args):
    installed = Path(gabfin.__file__).parent
    count = 0
    with zipfile.ZipFile(args.wheel) as archive:
        for name in archive.namelist():
            if name.startswith('gabfin/') and name.endswith('.py'):
                data = archive.read(name)
                assert (installed.parent/name).read_bytes() == data, name
                assert (args.source/'services'/name).read_bytes().replace(b'\r\n',b'\n') == data.replace(b'\r\n',b'\n'), name
                count += 1
    modules = tuple(item.name for item in pkgutil.walk_packages(gabfin.__path__, 'gabfin.'))
    for name in modules:
        importlib.import_module(name)
    assert find_spec('futu') is None
    assert find_spec('pandas') is None
    assert find_spec('exchange_calendars') is None
    actual = generate_schema()
    expected = json.loads((args.source/'schemas/gabfin-1.0.json').read_text())
    assert actual == expected
    return dict(installed_root=str(installed), python_modules_checked=count,
                modules_imported=len(modules), schema_matches=True, sdk_present=False,
                pandas_present=False, calendar_extra_present=False,
                wheel_sha256=hashlib.sha256(args.wheel.read_bytes()).hexdigest())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--wheel',type=Path,required=True)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    result = run(args)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
