// English / French. The English text is the key: a component writes t('Settings') and a missing French
// entry simply shows the English one. The choice is kept in this browser (localStorage) and, the first
// time, follows the language of the browser.

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type Lang = 'en' | 'fr'
const STORAGE_KEY = 'excel-filler-lang'

export function initialLang(): Lang {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY)
    if (saved === 'en' || saved === 'fr') return saved
  } catch { /* storage can be blocked: follow the browser */ }
  return (navigator.language || 'en').toLowerCase().startsWith('fr') ? 'fr' : 'en'
}

const FR: Record<string, string> = {
  // header and main page
  'Excel filler': 'Excel filler',
  'No workbook open': 'Aucun classeur ouvert',
  'Auto mode': 'Mode automatique',
  'Changes are applied without asking; a backup of the workbook is kept': 'Les modifications sont appliquées sans demander ; une sauvegarde du classeur est conservée',
  'Claude connected': 'Claude connecté',
  'Claude unreachable': 'Claude injoignable',
  'Claude answered': 'Claude a répondu',
  'Anthropic API key and model': 'Clé API Anthropic et modèle',
  Settings: 'Réglages',
  'Open another workbook…': 'Ouvrir un autre classeur…',
  'Open workbook…': 'Ouvrir un classeur…',
  'Connecting to the agent…': 'Connexion à l’agent…',
  'Claude cannot be reached.': 'Claude est injoignable.',
  Retry: 'Réessayer',
  Dismiss: 'Fermer',
  'Add your Anthropic API key in Settings to start.': 'Ajoutez votre clé API Anthropic dans les Réglages pour commencer.',
  'Stopping…': 'Arrêt en cours…',
  'Claude asked you a question: answer it below.': 'Claude vous pose une question : répondez ci-dessous.',
  'Your answer…': 'Votre réponse…',
  'Ask for a correction, e.g. “use the invoice date, not the due date”': 'Demandez une correction, par ex. « utilisez la date de facture, pas l’échéance »',
  'Follow-up request': 'Demande de suivi',
  Stop: 'Arrêter',
  Send: 'Envoyer',
  'Language': 'Langue',
  'Switch to French': 'Passer en français',
  'Switch to English': 'Passer en anglais',
  // job panel
  'Open the workbook to fill to start.': 'Ouvrez le classeur à remplir pour commencer.',
  Workbook: 'Classeur',
  'Choose a workbook…': 'Choisir un classeur…',
  'No .xlsx or .xlsm file in this folder.': 'Aucun fichier .xlsx ou .xlsm dans ce dossier.',
  'Sheets:': 'Feuilles :',
  'Claude decides': 'Claude décide',
  'Ticked sheets are the only ones that can be changed.': 'Seules les feuilles cochées peuvent être modifiées.',
  '{rows} rows × {cols} columns': '{rows} lignes × {cols} colonnes',
  Documents: 'Documents',
  All: 'Tous',
  None: 'Aucun',
  From: 'Depuis',
  'the workbook’s folder': 'le dossier du classeur',
  'Take the documents from another folder instead: pick any document in it': 'Prendre les documents d’un autre dossier : choisissez-y un document',
  'Change folder…': 'Changer de dossier…',
  'Use the workbook’s folder': 'Utiliser le dossier du classeur',
  'Filter…': 'Filtrer…',
  'Filter documents': 'Filtrer les documents',
  'No PDF or image in this folder yet.': 'Aucun PDF ni image dans ce dossier.',
  'No document matches': 'Aucun document ne correspond à',
  'Add files…': 'Ajouter des fichiers…',
  'Add the PDFs and images of another folder: pick any document in it': 'Ajouter les PDF et images d’un autre dossier : choisissez-y un document',
  'Add folder…': 'Ajouter un dossier…',
  Instructions: 'Instructions',
  '(optional)': '(facultatif)',
  'e.g. amounts excluding VAT, one row per line item': 'par ex. montants hors taxe, une ligne par article',
  'Work on a copy': 'Travailler sur une copie',
  'the original is not changed': 'l’original n’est pas modifié',
  'the agent writes into the workbook itself': 'l’agent écrit dans le classeur lui-même',
  'The workbook is copied next to the original (for example costs (copy).xlsx) and the copy is filled. The original is not changed.':
    'Le classeur est copié à côté de l’original (par ex. costs (copy).xlsx) et la copie est remplie. L’original n’est pas modifié.',
  'changes are saved without asking': 'les modifications sont enregistrées sans demander',
  'you approve each change': 'vous approuvez chaque modification',
  'Changes are applied without asking you; questions are not asked (missing values are left empty and listed)':
    'Les modifications sont appliquées sans vous demander ; aucune question n’est posée (les valeurs manquantes restent vides et sont listées)',
  'Fill workbook': 'Remplir le classeur',
  'Keep a copy of {name} first: the agent writes into it.': 'Gardez d’abord une copie de {name} : l’agent écrit dedans.',
  'the workbook': 'le classeur',
  // activity feed
  'Fill a workbook from your documents': 'Remplir un classeur à partir de vos documents',
  'Something went wrong.': 'Une erreur est survenue.',
  'Did not work:': 'Échec :',
  'is updated.': 'est mis à jour.',
  'The previous version is kept in': 'La version précédente est conservée dans',
  'Open in Excel': 'Ouvrir dans Excel',
  'Working…': 'Travail en cours…',
  'Stopped.': 'Arrêté.',
  'Starting: Claude receives the workbook and the documents…': 'Démarrage : Claude reçoit le classeur et les documents…',
  'Claude is thinking…': 'Claude réfléchit…',
  'Claude is writing…': 'Claude écrit…',
  'Waiting for your approval…': 'En attente de votre approbation…',
  'Waiting for your answer…': 'En attente de votre réponse…',
  'Claude is looking at the result…': 'Claude examine le résultat…',
  'Claude is working…': 'Claude travaille…',
  'Reading the workbook': 'Lecture du classeur',
  'Preparing changes to the workbook': 'Préparation des modifications du classeur',
  'Reading a document': 'Lecture d’un document',
  'Looking at an image': 'Examen d’une image',
  'Reading a file': 'Lecture d’un fichier',
  'Looking at the folder': 'Examen du dossier',
  'Asking you a question': 'Question posée à vous',
  'Searching the reference texts': 'Recherche dans les textes de référence',
  'Filling cells': 'Remplissage des cellules',
  // changes and questions
  Cell: 'Cellule',
  Now: 'Actuel',
  'New value': 'Nouvelle valeur',
  Format: 'Format',
  empty: 'vide',
  '… and {n} more cell(s)': '… et {n} cellule(s) de plus',
  Approve: 'Approuver',
  Reject: 'Rejeter',
  Always: 'Toujours',
  'Your answer': 'Votre réponse',
  Skip: 'Passer',
  // settings
  'Add your Anthropic API key': 'Ajoutez votre clé API Anthropic',
  'Excel filler uses Claude through your own Anthropic account; Anthropic bills you directly for what you use.':
    'Excel filler utilise Claude avec votre propre compte Anthropic ; Anthropic vous facture directement ce que vous utilisez.',
  'Get a key': 'Obtenir une clé',
  'Get a key at': 'Obtenir une clé sur',
  'A key ending in': 'Une clé se terminant par',
  'is saved. Paste a new one to replace it.': 'est enregistrée. Collez-en une nouvelle pour la remplacer.',
  'Currently using the Azure Foundry setup of this PC. A key saved here is used instead.': 'Le réglage Azure Foundry de ce PC est utilisé. Une clé enregistrée ici le remplace.',
  'API key': 'Clé API',
  Hide: 'Masquer',
  Show: 'Afficher',
  Model: 'Modèle',
  'Default (recommended)': 'Par défaut (recommandé)',
  'Claude Opus 5.5 (most capable)': 'Claude Opus 5.5 (le plus capable)',
  'Claude Sonnet 5.5 (faster, cheaper)': 'Claude Sonnet 5.5 (plus rapide, moins cher)',
  'Claude Haiku 4.5 (fastest, cheapest)': 'Claude Haiku 4.5 (le plus rapide, le moins cher)',
  'The key is stored for your Windows account (Credential Manager) and sent only to Anthropic.': 'La clé est stockée pour votre compte Windows (gestionnaire d’identifiants) et envoyée seulement à Anthropic.',
  'This PC has no secure storage for keys: the key will not be remembered after you close the app.': 'Ce PC n’a pas de stockage sécurisé : la clé ne sera pas conservée après la fermeture de l’application.',
  'Remove key': 'Supprimer la clé',
  Close: 'Fermer',
  'Testing…': 'Test en cours…',
  'Test and save': 'Tester et enregistrer',
  // small components
  'Copy this message': 'Copier ce message',
  'Copied ✓': 'Copié ✓',
  Copy: 'Copier',
  'Resize the side panel': 'Redimensionner le panneau latéral',
  'Drag to resize; double-click to reset': 'Glisser pour redimensionner ; double-clic pour réinitialiser',
  'The window could not show the agent\'s progress.': 'La fenêtre n’a pas pu afficher la progression de l’agent.',
  'The job may still be running. Reloading the window shows its current state; the error was written to the log file.':
    'Le travail peut encore être en cours. Recharger la fenêtre montre son état actuel ; l’erreur a été écrite dans le journal.',
  'Reload the window': 'Recharger la fenêtre',
}

// Texts with a variable part, from the engine or built in state.ts: tried after the exact match.
const PATTERNS: [RegExp, string][] = [
  [/^Waiting for your approval: /, 'En attente de votre approbation : '],
  [/^Apply these cell changes to (.+)\?$/, 'Appliquer ces modifications de cellules à $1 ?'],
  [/(^|, |: )sheet /g, '$1feuille '],
  [/ = empty(?=,| and |$)/g, ' = vide'],
  [/ and (\d+) more$/, ' et $1 de plus'],
  [/^Fill (.+?) from (.+)$/, 'Remplir $1 à partir de $2'],
  [/^Fill (.+)$/, 'Remplir $1'],
]

export function translate(text: string, lang: Lang, vars?: Record<string, string | number>): string {
  let out = text
  if (lang === 'fr' && text) {
    if (FR[text] !== undefined) out = FR[text]
    else {
      const split = /^([^:]{3,60}): (.*)$/.exec(text)  // "Reading a document: invoice.pdf, page 1"
      if (split && FR[split[1]] !== undefined) out = `${FR[split[1]]} : ${translate(split[2], lang)}`
      else for (const [pattern, replacement] of PATTERNS) out = out.replace(pattern, replacement)
    }
  }
  if (vars) for (const [name, value] of Object.entries(vars)) out = out.split(`{${name}}`).join(String(value))
  return out
}

type Value = { lang: Lang; setLang: (lang: Lang) => void; t: (text: string, vars?: Record<string, string | number>) => string }
const LangContext = createContext<Value>({ lang: 'en', setLang: () => {}, t: (text, vars) => translate(text, 'en', vars) })

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang)
  const setLang = useCallback((next: Lang) => {
    setLangState(next)
    try { window.localStorage.setItem(STORAGE_KEY, next) } catch { /* not kept: the choice lasts until the window closes */ }
  }, [])
  useEffect(() => { document.documentElement.lang = lang }, [lang])
  const value = useMemo<Value>(() => ({ lang, setLang, t: (text, vars) => translate(text, lang, vars) }), [lang, setLang])
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>
}

export const useLang = () => useContext(LangContext)
export const useT = () => useContext(LangContext).t
