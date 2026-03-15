# Resume Tailoring Agent — specyfikacja v1

## 1. Cel projektu
System ma automatycznie dopasowywać CV oraz opcjonalnie list motywacyjny do konkretnej oferty pracy, wyłącznie na podstawie prawdziwych danych kandydata.

Celem systemu jest zwiększenie trafności i jakości aplikacji poprzez:
- lepsze dopasowanie treści CV do wymagań oferty,
- wyeksponowanie najbardziej adekwatnych doświadczeń i umiejętności,
- wykrywanie oraz uwzględnianie istotnych słów kluczowych,
- ograniczenie czasu potrzebnego na ręczne edytowanie dokumentów aplikacyjnych.

## 2. Problem, który rozwiązuje
Ręczne dopasowywanie CV do każdej oferty pracy jest czasochłonne, podatne na błędy i często prowadzi do pomijania ważnych słów kluczowych, wymagań lub najbardziej trafnych doświadczeń.

Dodatkowo kandydat może mieć trudność z obiektywną oceną:
- czy rzeczywiście pasuje do danej oferty,
- które elementy doświadczenia warto uwypuklić,
- których informacji nie należy dodawać, ponieważ nie mają pokrycia w rzeczywistym profilu.

## 3. Użytkownik
Docelowym użytkownikiem systemu jest jedna osoba — kandydat, który chce szybko generować dopasowane CV pod konkretne ogłoszenie, bez potrzeby ręcznego edytowania dokumentów dla każdej oferty pracy.

## 4. Wejście do systemu
System przyjmuje następujące dane wejściowe:
- profil kandydata (master profile / baza doświadczeń, umiejętności, projektów, wykształcenia i osiągnięć),
- treść oferty pracy,
- opcjonalnie aktualne CV użytkownika,
- opcjonalnie informację, czy należy wygenerować również list motywacyjny.

W wersji v1 oferta pracy może być dostarczona w jednej z poniższych form:
- tekst wklejony ręcznie,
- pojedynczy adres URL do konkretnej oferty,
- opcjonalnie plik zawierający treść oferty.

## 5. Wyjście z systemu
System zwraca:
- dopasowane CV w formacie DOCX,
- raport dopasowania i zmian,
- opcjonalnie list motywacyjny.

Raport powinien zawierać co najmniej:
- ogólną ocenę dopasowania kandydata do oferty,
- klasyfikację zgodności, np. wysoka / średnia / niska,
- listę wymagań spełnionych,
- listę wymagań częściowo spełnionych,
- listę wymagań niespełnionych,
- listę słów kluczowych wykrytych w ofercie,
- wskazanie, które elementy profilu zostały uwypuklone w CV,
- wskazanie, których informacji celowo nie dodano z powodu braku pokrycia w danych kandydata.

## 6. Zakres v1
System ma:
- analizować pojedynczą ofertę pracy,
- identyfikować wymagania, obowiązki oraz słowa kluczowe w ogłoszeniu,
- kłaść szczególny nacisk na detekcję i sensowne wykorzystanie słów kluczowych,
- porównywać ofertę z profilem kandydata,
- oceniać poziom dopasowania kandydata do oferty,
- generować dopasowaną treść CV,
- opcjonalnie generować list motywacyjny,
- wypełniać szablon DOCX,
- zapisywać wynik lokalnie,
- generować raport zmian i raport dopasowania,
- wskazywać sytuacje, w których dopasowanie do oferty jest zbyt niskie, aby rekomendować generowanie CV.

System nie ma:
- automatycznie aplikować na oferty pracy,
- wykonywać masowego scrapingu portali z ofertami pracy,
- samodzielnie przeszukiwać wielu portali na dużą skalę w wersji v1,
- wymyślać doświadczeń, projektów, technologii, certyfikatów ani umiejętności,
- zawyżać poziomu dopasowania użytkownika do oferty,
- budować rozbudowanego multi-agent systemu na start.

## 7. Zakres poza v1 / rozwój w przyszłości
W kolejnych wersjach system może zostać rozszerzony o:
- filtrowanie i rekomendowanie ofert pracy na podstawie profilu użytkownika,
- integrację z portalami typu Pracuj.pl, Just Join IT, No Fluff Jobs, LinkedIn itp.,
- półautomatyczne pobieranie treści ofert,
- obsługę wielu szablonów CV,
- ranking ofert najbardziej dopasowanych do profilu użytkownika,
- rozbudowany system agentowy lub dodatkowe moduły walidacyjne.

## 8. Twarde zasady
System musi działać zgodnie z następującymi zasadami:
- nie wolno dopisywać nieprawdziwych informacji,
- nie wolno zawyżać lat doświadczenia,
- nie wolno dodawać technologii, których kandydat nie używał,
- nie wolno dopisywać projektów, stanowisk ani certyfikatów bez pokrycia w danych wejściowych,
- każda istotna zmiana musi mieć pokrycie w profilu kandydata,
- wszelkie istotne zmiany muszą być jasno wskazane w raporcie,
- brak danych nie może być interpretowany jako spełnienie wymagania,
- system ma preferować ostrożność i prawdziwość ponad „lepsze brzmienie” CV.

## 9. Tryb działania v1
System działa w trybie półautomatycznym:
1. użytkownik dostarcza profil kandydata,
2. użytkownik dostarcza ofertę pracy,
3. system analizuje ofertę,
4. system porównuje ofertę z profilem,
5. system ocenia poziom dopasowania,
6. system generuje propozycję CV,
7. system generuje raport zmian,
8. użytkownik ręcznie przegląda i akceptuje finalny dokument.

## 10. Ograniczenia v1
- system obsługuje pojedynczą ofertę pracy na jedno uruchomienie,
- system nie gwarantuje otrzymania zaproszenia na rozmowę kwalifikacyjną,
- system wspiera użytkownika, ale nie podejmuje ostatecznej decyzji o aplikowaniu,
- użytkownik odpowiada za końcową weryfikację dokumentów przed wysłaniem,
- jakość wyniku zależy od jakości i kompletności profilu kandydata oraz treści oferty.

## 11. Kryteria sukcesu v1
Projekt zostanie uznany za udany, jeśli:
- użytkownik może wkleić ofertę pracy lub podać pojedynczy link do oferty,
- system generuje sensowne CV w formacie DOCX,
- wynik jest czytelny i nadaje się do ręcznej korekty,
- CV jest lepiej dopasowane do oferty niż wersja bazowa,
- system poprawnie wykrywa kluczowe wymagania i słowa kluczowe,
- system nie halucynuje,
- raport zmian jasno pokazuje logikę działania systemu,
- system potrafi wskazać, że dana oferta jest słabo dopasowana do profilu użytkownika.

## 12. Metryki jakości
W celu oceny jakości działania systemu należy brać pod uwagę:
- poprawność wykrycia wymagań z oferty,
- poprawność wykrycia słów kluczowych,
- stopień pokrycia wymagań oferty przez profil użytkownika,
- liczbę zmian wymagających ręcznej korekty po wygenerowaniu CV,
- brak nieprawdziwych lub niepotwierdzonych informacji,
- subiektywną ocenę użyteczności wygenerowanego CV względem wersji bazowej.

## 13. Prywatność i bezpieczeństwo
- dane kandydata są traktowane jako poufne,
- profil kandydata, historia analiz oraz wygenerowane dokumenty są przechowywane lokalnie w wersji v1,
- użytkownik powinien mieć możliwość usunięcia zapisanych danych lokalnych,
- system nie może ujawniać danych użytkownika poza procesem niezbędnym do analizy i generowania dokumentów,
- wszelkie operacje na danych powinny być ograniczone do minimum koniecznego do działania systemu.

## 14. Technologie na start
Wersja v1 będzie oparta o:
- Python,
- FastAPI,
- OpenAI API,
- SQLite,
- docxtpl / python-docx,
- VS Code.

## 15. Sposób uruchamiania
System w wersji v1 ma być uruchamiany lokalnie na komputerze użytkownika, bez wdrożenia chmurowego.

Zakładany sposób pracy:
- backend uruchamiany lokalnie,
- dane przechowywane lokalnie,
- generowanie dokumentów wykonywane lokalnie,
- model językowy wykorzystywany przez API.

## 16. Główna wartość projektu
Projekt ma być jednocześnie:
- praktycznym narzędziem do codziennego użytku,
- przykładowym produktem do portfolio,
- demonstracją umiejętności z zakresu AI engineering, backendu, automatyzacji i generowania dokumentów.