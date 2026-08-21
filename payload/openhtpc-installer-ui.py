#!/usr/bin/env python3
"""Retro terminal presentation for the single OPENHTPC installer state machine."""
import argparse,os,shutil,sys
BLUE="\033[38;5;39m"; CYAN="\033[38;5;51m"; ORANGE="\033[38;5;208m"; RESET="\033[0m"
STAGES=("SYSTÈME","MATÉRIEL","DÉPENDANCES","RUNTIME","CONFIGURATION","INSTALLATION","VALIDATION")
DVD_DESCRIPTIONS={"lsdvd":"Permet d’analyser la structure du DVD et d’identifier le titre principal.","util-linux":"Fournit l’éjection physique sûre du lecteur.","udisks2":"Fournit la gestion sûre des volumes optiques.","libdvdnav":"Fournit la navigation dans les DVD vidéo."}
CONSENTS={"dvd-tools":("SUPPORT DES DVD VIDÉO",()),"dvd-css":("Lecture des DVD commerciaux",("RPM Fusion Free","RPM Fusion Free Tainted","libdvdcss"))}
def capable(stream=sys.stdout,env=os.environ,size=None):
 size=size or shutil.get_terminal_size((80,24)); return stream.isatty() and env.get("TERM","dumb")!="dumb" and size.columns>=72 and size.lines>=20
def logo(color=True):
 c=BLUE if color else ""; a=ORANGE if color else ""; r=RESET if color else ""
 return f"{c}      ╭─────╮  ▷ ║ {a}▐{c}  OPENHTPC{r}\n{c}      ╰─────╯    ║ {a}▐{c}  OPEN · MODULAR · EXTENSIBLE{r}"
def render(stage,status="active",width=78):
 marks={"done":"✓","active":">","warning":"!","failed":"X","pending":" "}; active=STAGES.index(stage) if stage in STAGES else 0
 lines=["╔"+"═"*(width-2)+"╗",logo(sys.stdout.isatty()),"╠"+"═"*(width-2)+"╣"]
 for i,name in enumerate(STAGES): lines.append(f"║ [{marks['done' if i<active else status if i==active else 'pending']}] {name:<66} ║")
 progress=round((active+1)*20/len(STAGES)); percent=round((active+1)*100/len(STAGES))
 lines += ["╠"+"═"*(width-2)+"╣",f"║ Progression [{'\u2588'*progress}{'░'*(20-progress)}] {percent:>3}%{' '*(width-43)}║",f"║ Journal : ~/.local/state/openhtpc/install.log{' '*(width-50)}║","╚"+"═"*(width-2)+"╝"]
 return "\n".join(lines)
def consent_box(kind,packages=(),width=76):
 title,items=CONSENTS[kind]; rows=[f"╔{'═'*(width-2)}╗",f"║ {title:<{width-4}} ║",f"╠{'═'*(width-2)}╣"]
 if kind=="dvd-tools":
  rows += [f"║ {'Pour identifier et lire correctement les DVD vidéo, OPENHTPC doit ajouter':<{width-4}} ║",f"║ {'certains composants absents de votre installation Fedora actuelle.':<{width-4}} ║",f"║ {'Composants requis :':<{width-4}} ║"]
  for package in packages:
   rows += [f"║  {package:<{width-5}} ║",f"║    {DVD_DESCRIPTIONS.get(package,'Composant requis par le support DVD.'):<{width-7}} ║"]
  rows += [f"║ {'Fedora demandera votre mot de passe pour installer uniquement ces composants.':<{width-4}} ║",f"║ {'OPENHTPC ne connaît, ne stocke et ne journalise jamais votre mot de passe.':<{width-4}} ║",f"║ {'Aucune mise à niveau générale de Fedora ne sera effectuée.':<{width-4}} ║",f"║ {'Aucun autre logiciel ne sera installé volontairement.':<{width-4}} ║"]
 else: rows.extend(f"║  • {item:<{width-6}}║" for item in items)
 rows += [f"║{' '*(width-2)}║",f"║  INSTALLER / IGNORER{' '*(width-24)}║",f"╚{'═'*(width-2)}╝"]; return "\n".join(rows)
def dvd_progress(step,packages=()):
 marks={"check":"✓ Vérification des dépendances","install":"→ Installation de "+", ".join(packages),"verify":"→ Vérification","done":"✓ Support DVD opérationnel"}
 return "Installation du support DVD…\n"+marks[step]
def main():
 p=argparse.ArgumentParser(); p.add_argument("--stage",choices=STAGES); p.add_argument("--consent",choices=CONSENTS); p.add_argument("--dvd-progress",choices=("check","install","verify","done")); p.add_argument("--packages",nargs="*"); p.add_argument("--success",action="store_true"); a=p.parse_args()
 size=shutil.get_terminal_size((80,24))
 if sys.stdout.isatty() and os.environ.get("TERM","dumb")!="dumb" and (size.columns<72 or size.lines<20):
  print("Fenêtre trop petite. Taille minimale recommandée : 72 x 20."); return 2
 if not capable(size=size): print("OPENHTPC interactive interface unavailable. Using text installation mode."); return 2
 if a.success: print(logo()); print("\n╔════════ OPENHTPC — INSTALLATION TERMINÉE ════════╗\n║ Hardware Passport  ✓   Runtime MPV  ✓            ║\n║ Flex Launcher      ✓   DVD          ✓            ║\n║ Média local        ✓   Autostart    ✓            ║\n║ TMDb                    À configurer               ║\n║                 SYSTÈME PRÊT                      ║\n╚═══════════════════════════════════════════════════╝"); return 0
 if a.consent: print(consent_box(a.consent,a.packages or ())); return 0
 if a.dvd_progress: print(dvd_progress(a.dvd_progress,a.packages or ())); return 0
 print("\033[2J\033[H"+render(a.stage or "SYSTÈME")); return 0
if __name__=="__main__": raise SystemExit(main())
