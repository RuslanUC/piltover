---types---

langPackString#cad181f6 key:string value:string = LangPackString;
langPackStringPluralized#6c47ac9f key:string zero_value:string one_value:string two_value:string few_value:string many_value:string other_value:string = LangPackString;
langPackStringDeleted#2979eeb2 key:string = LangPackString;
langPackDifference#f385c1f6 lang_code:string from_version:int version:int strings:Vector<LangPackString> = LangPackDifference;
langPackLanguage#117698f1 name:string native_name:string lang_code:string = LangPackLanguage;

---functions---

langpack.getLangPack#9ab5c58e lang_code:string = LangPackDifference;
langpack.getStrings#2e1ee318 lang_code:string keys:Vector<string> = Vector<LangPackString>;
langpack.getDifference#b2e4d7d from_version:int = LangPackDifference;
langpack.getLanguages#800fd57d = Vector<LangPackLanguage>;

// LAYER 72
// This schema is not full, for now it contains only methods that are need to Telegram for Android to work
