"""Generate the shared JSON schema directly from public Python contracts."""
import importlib,inspect,pkgutil,json
from enum import Enum
from typing import Union
from pydantic import BaseModel,TypeAdapter

def generate_schema():
    import gabfin.contracts as package
    public={}
    for info in pkgutil.iter_modules(package.__path__):
        if info.name=='schema':continue
        module=importlib.import_module(package.__name__+'.'+info.name)
        for name,cls in vars(module).items():
            if name.startswith('_') or not inspect.isclass(cls) or cls.__module__!=module.__name__:continue
            if issubclass(cls,(BaseModel,Enum)):public[cls.__module__+'.'+name]=cls
    result=TypeAdapter(Union[tuple(public[k] for k in sorted(public))]).json_schema(mode='serialization')
    result['$schema']='https://json-schema.org/draft/2020-12/schema'
    result['x-gabfin-schema-version']='1.0'
    return result

if __name__=='__main__':
    import sys
    from pathlib import Path
    Path(sys.argv[1]).write_text(json.dumps(generate_schema(),indent=2,sort_keys=True)+'\n',encoding='utf-8')
