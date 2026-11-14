"""Optional OPENHTPC lab Beta wall composition from canonical CORE pages only.

Never mutates MEDIA manifests or touches physical media.
"""
import pathlib
import re

_PAGE=re.compile(r"(?m)^\[(MEDIA_D[0-9a-f]{8})\]\s*$")
_LINE=lambda name: re.compile(r"(?m)^"+re.escape(name)+r"=(.*)$")

def wall_from_core(media_sections, home, serialize, fallback_icon):
    if not isinstance(media_sections, str): return None
    matches=list(_PAGE.finditer(media_sections))
    poster_root=(pathlib.Path(home)/".cache/openhtpc/media/artwork").resolve()
    works=[]
    seen=set()
    for n,found in enumerate(matches):
        sec=found.group(1)
        if sec in seen: continue
        seen.add(sec)
        end=matches[n+1].start() if n+1<len(matches) else len(media_sections)
        # Slice includes nested sections; stop at the next header of any kind.
        block=media_sections[found.end():end].split("\n[",1)[0]
        lines={}
        for key in ("Title","Poster","Metadata","Fact2"):
            value=_LINE(key).search(block)
            lines[key]=value.group(1).strip() if value else ""
        # Present only identified works with a real locally cached movie poster.
        if not lines["Title"] or "TMDB" not in lines["Fact2"].upper(): continue
        if ";" in lines["Title"] or "\n" in lines["Title"]: continue
        try:
            poster=pathlib.Path(lines["Poster"]).resolve(strict=True)
            if not poster.is_file() or not poster.is_relative_to(poster_root):continue
        except (OSError, RuntimeError):continue
        year=re.search(r"(?:19|20)\d{2}",lines["Metadata"])
        title=lines["Title"]+(" ("+year.group(0)+")" if year else "")
        works.append((title,poster,sec))
    works.sort(key=lambda item:(item[0].casefold(),item[2]))
    if not works:return None
    lines=["[MEDIA_WALL]","Layout=MediaWall"]
    for number,(title,poster,sec) in enumerate(works,1):
        lines.append(serialize(number,title,poster,":submenu "+sec))
    return "\n".join(lines)
