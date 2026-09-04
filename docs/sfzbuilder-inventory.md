# SFZ Builder: Function Inventory

Status: reference.
Date: 2026-09-03.

This document is written in ASD-STE100 (Simplified Technical English).

## 1. Purpose

This document lists all the functions of the SFZ builder before the new design.
Use this list to test commit 1. Commit 1 must keep all of these functions.
Commit 1 must also keep the same appearance.

## 2. Files

| Path | Contents |
|---|---|
| `html/index.html` lines 1124 to 1181 | The markup. The root element is `#sfzbuilder-library`. |
| `html/index.html` line 736 | The menu icon `#mod-sfzbuilder`. |
| `html/js/desktop.js` lines 149 to 150 | The window connection. |
| `html/js/sfzbuilder.js` | 579 lines. The class `sfzBuilderBox`. |
| `html/css/less/sfzbuilder.less` | 453 lines. LESS compiles it into `main.css`. |
| `mod/sfzbuilder.py` | The server logic. |
| `mod/webserver.py` lines 2608 to 2615 | The routes. |
| `test/test_sfzbuilder.py` | 248 lines. The Python tests. |

The tools `grunt` and `lessc` are in `html/css/node_modules/.bin/`.

## 3. Endpoints

The new design must not change these endpoints.

| Method | Path | Result |
|---|---|---|
| GET | `/sfzbuilder/banks` | The names of the banks. |
| GET | `/sfzbuilder/bank?name=` | The base note and the pads of one bank. |
| POST | `/sfzbuilder/bank` | Makes a bank directory. |
| GET | `/sfzbuilder/samples?bank=` | The audio files in one bank. |
| GET | `/sfzbuilder/device?exclude_bank=` | The audio files in the user directory. |
| GET | `/sfzbuilder/usb` | The audio files on the USB devices. |
| POST | `/sfzbuilder/upload` | Puts audio files in a bank. |
| GET | `/sfzbuilder/audio/<name>` | Sends one audio file for the preview. |
| POST | `/sfzbuilder/build` | Writes `bank.sfz` and `bank.json`. |

## 4. The function list

Test each item. Each item must operate after commit 1.

### Banks

1. The panel shows the list of the banks.
2. You can select a bank. The selected bank has a different color.
3. You can make a bank. Click "Add Bank". An input box opens.
4. The Enter key accepts the new name.
5. The Escape key cancels the new name. A click on a different element also cancels it.
6. The panel reads the pads of a bank from `bank.json`.

### Pads

7. The number of the pads is 1 to 128.
8. A change to the number of the pads keeps each pad at its index.
9. The base note is 0 to 127.
10. The panel shows the name of the base note. The range is C-1 to G9.
11. The note of a pad is the base note plus the index.
12. A pad shows the note number and the note name.
13. A pad shows "out of range" if the note is more than 127.
14. Each full pad has a gain control. The range is -144 to 48.
15. Each full pad has a root note control. The range is 0 to 127. An empty box is automatic.
16. Each full pad has a loop control. The values are `one_shot` and `no_loop`.
17. You can make a pad empty. Click the multiplication sign.
18. A click on a pad selects it. A second click on the same pad cancels the selection.

### Samples

19. You can select the source of the samples. The sources are the bank, the device and the USB.
20. You can filter the samples by name. The filter ignores the case of the letters.
21. You can send audio files to the selected bank. A bank must be selected first.
22. You can hear one sample. Click the play control.
23. A second click stops the sample.
24. Only one sample sounds at a time.
25. The sound stops when you close the panel. It also stops when you select a different bank.
26. An error message shows if the browser cannot play the sample.

### Assignment

27. You can put a sample on a pad with a drag. Each pad is a drop target.
28. The drag shows a helper element with the name of the sample.
29. You can also put a sample on a pad with two clicks. Click the pad, then click the sample.
30. An error message shows if you click a sample and no pad is selected.

### Build

31. The build needs a selected bank.
32. The build needs one full pad as a minimum.
33. The build sends an empty value for each empty pad. Thus the notes of the other pads do not change.
34. The panel shows the name of the file and the number of the samples after the build.

### Other

35. The panel shows a status line. An error is red.
36. The panel shows help text if no bank is selected.
37. The pads and the toolbar are not visible if no bank is selected.

## 5. Known problems

These are problems in the design before commit 1.
Commit 2 can correct them. Commit 1 must not correct them.

1. There is no waveform. The preview has no position control and no trim control.
2. The pad grid has no keyboard shape and no octave marks.
3. Each pad has three input boxes. The grid looks complex.
4. The build is manual. The panel saves nothing automatically.
5. You cannot put many samples on many pads with one action.
6. There is no automatic chromatic map.
7. There is no round robin.
8. You cannot rename, copy or delete a bank.
9. The panel does not show the pads of the pi-stomp hardware.
10. You cannot drop a file from the desktop. You must use the upload control.
11. `renderSlots` makes all the pads again after each change.
    With 128 pads the panel makes 128 drop targets again.
    Thus the panel loses the focus and the scroll position.
12. `renderSamples` calls `stopPreview`. Thus the filter stops the sound.
13. The menu icon is four squares. The icon does not show the function.
