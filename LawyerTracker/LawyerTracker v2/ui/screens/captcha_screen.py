"""
captcha_screen.py

Displays the CAPTCHA image exactly as received from eCourts, a text
box for entry, a Refresh button, and Submit.

Two modes (selected via segmented control):
  - Manual: blank text box, user reads the image and types it in.
  - OCR-assisted: KevinOCR runs on the current image and PRE-FILLS the
    text box with its best guess. The box stays editable and Submit
    still requires an explicit click - OCR never submits by itself.
    If KevinOCR isn't configured/available, this mode is disabled and
    only Manual is offered.

The screen always waits for the user to click Submit before any search
request is sent - there is no automatic submission path here.
"""
from __future__ import annotations

import io
import tempfile
import threading

import customtkinter as ctk
from PIL import Image

from models.enums import CaptchaMode, SearchType
from ui import theme
from app_utils.logger import get_logger

logger = get_logger(__name__)


class CaptchaScreen(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._image_bytes: bytes = b""
        self._image_tmp_path: str = ""
        self._current_ctk_image = None
        self._mode = CaptchaMode.MANUAL

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        card = ctk.CTkFrame(self, width=440, corner_radius=theme.CARD_RADIUS)
        card.grid(row=0, column=0, pady=20)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(card, text="Verify CAPTCHA", font=theme.font_heading()).grid(
            row=0, column=0, padx=36, pady=(28, 2), sticky="w"
        )
        ctk.CTkLabel(
            card, text="Step 2 of 2 - confirm the CAPTCHA to run your search.",
            font=theme.font_body(), text_color=theme.COLOR_MUTED,
        ).grid(row=1, column=0, padx=36, pady=(0, 20), sticky="w")

        image_frame = ctk.CTkFrame(
            card, fg_color=("#F3F4F6", "#20242F"), corner_radius=8, height=90,
        )
        image_frame.grid(row=2, column=0, padx=36, pady=(0, 12), sticky="ew")
        image_frame.grid_propagate(False)
        image_frame.grid_columnconfigure(0, weight=1)
        image_frame.grid_rowconfigure(0, weight=1)

        self.image_label = ctk.CTkLabel(image_frame, text="")
        self.image_label.grid(row=0, column=0)
        self.image_label.grid_remove()  # shown only once an image is actually loaded

        # Separate label for "Loading CAPTCHA..." / "Could not load..."
        # text. Kept distinct from image_label on purpose: reusing one
        # label for both text and image, toggling `image=None` back and
        # forth, corrupts CustomTkinter/Tk's internal image-option cache
        # and crashes the *next* image load with
        # `_tkinter.TclError: image "pyimageN" doesn't exist` - this bit
        # us on the second search in testing. Two labels, one always
        # image-only and one always text-only, sidesteps that entirely.
        self.captcha_loading_label = ctk.CTkLabel(
            image_frame, text="Loading CAPTCHA...", text_color=theme.COLOR_MUTED
        )
        self.captcha_loading_label.grid(row=0, column=0)

        self.refresh_button = ctk.CTkButton(
            card, text="\u21bb  Refresh CAPTCHA", command=self._refresh_captcha,
            fg_color="transparent", border_width=1,
            border_color=("#C7CAD1", "#39404F"), text_color=("#1B1E27", "#E7E9EE"),
            hover_color=("#ECEEF1", "#242835"), height=32,
        )
        self.refresh_button.grid(row=3, column=0, padx=36, pady=(0, 16))

        self.mode_switch = ctk.CTkSegmentedButton(
            card, values=["Manual", "OCR-assisted"], command=self._on_mode_changed
        )
        self.mode_switch.set("Manual")
        self.mode_switch.grid(row=4, column=0, padx=36, pady=(0, 12))

        self.suggest_button = ctk.CTkButton(
            card, text="\u2728  Suggest with KevinOCR", command=self._suggest_with_ocr,
            state="disabled", height=32,
        )
        self.suggest_button.grid(row=5, column=0, padx=36, pady=(0, 12))
        self.suggest_button.grid_remove()  # only shown in OCR-assisted mode

        self.captcha_entry = ctk.CTkEntry(
            card, placeholder_text="Type the CAPTCHA text", height=38, justify="center",
            font=ctk.CTkFont(size=15),
        )
        self.captcha_entry.grid(row=6, column=0, padx=36, pady=(0, 10), sticky="ew")
        self.captcha_entry.bind("<Return>", lambda _e: self._submit())

        self.status_label = ctk.CTkLabel(card, text="", text_color=theme.COLOR_MUTED, font=theme.font_small())
        self.status_label.grid(row=8, column=0, padx=36, pady=(0, 12))

        self.submit_button = ctk.CTkButton(
            card, text="Submit", command=self._submit, height=38, font=ctk.CTkFont(weight="bold"),
        )
        self.submit_button.grid(row=9, column=0, padx=36, pady=(0, 32), sticky="ew")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_show(self) -> None:
        self.captcha_entry.delete(0, "end")
        self.status_label.configure(text="")

        # Respect the CAPTCHA method chosen upfront on the Home screen.
        requested_mode = self.app.pending_search.get("captcha_mode", CaptchaMode.MANUAL.value)
        if requested_mode == CaptchaMode.OCR_ASSISTED.value and self.app.captcha_service.ocr_available():
            self.mode_switch.set("OCR-assisted")
            self._mode = CaptchaMode.OCR_ASSISTED
            self.suggest_button.grid()
        else:
            self.mode_switch.set("Manual")
            self._mode = CaptchaMode.MANUAL
            self.suggest_button.grid_remove()

        self._refresh_captcha()

    # ------------------------------------------------------------------
    # CAPTCHA image loading
    # ------------------------------------------------------------------

    def _refresh_captcha(self) -> None:
        self.image_label.grid_remove()
        self.captcha_loading_label.configure(text="Loading CAPTCHA...")
        self.captcha_loading_label.grid()
        self.refresh_button.configure(state="disabled")
        threading.Thread(target=self._fetch_captcha_worker, daemon=True).start()

    def _fetch_captcha_worker(self) -> None:
        try:
            image_bytes = self.app.captcha_service.fetch_image_bytes()
        except Exception as exc:
            logger.exception("Failed to fetch CAPTCHA.")
            # Capture the message now, not inside the lambda: Python
            # unbinds `exc` the moment this except block ends, but
            # self.after() runs the lambda later on the main thread -
            # by then `exc` would raise NameError instead of showing
            # the actual error.
            error_message = str(exc)
            self.after(0, lambda: self._on_captcha_error(error_message))
            return
        self.after(0, self._apply_captcha_image, image_bytes)

    def _on_captcha_error(self, message: str) -> None:
        self.refresh_button.configure(state="normal")
        self.image_label.grid_remove()
        self.captcha_loading_label.configure(text="Could not load CAPTCHA.")
        self.captcha_loading_label.grid()
        self.app.show_error("CAPTCHA error", message)

    def _apply_captcha_image(self, image_bytes: bytes) -> None:
        self._image_bytes = image_bytes
        pil_image = Image.open(io.BytesIO(image_bytes))
        ctk_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image,
                                  size=pil_image.size)
        # Keep a strong reference on self so this CTkImage isn't
        # garbage-collected while still displayed.
        self._current_ctk_image = ctk_image
        self.captcha_loading_label.grid_remove()
        self.image_label.configure(image=ctk_image)
        self.image_label.grid()
        self.refresh_button.configure(state="normal")

        # Persist to a temp file too, since KevinOCR's engine.predict()
        # takes an image path rather than raw bytes.
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.write(image_bytes)
        tmp.close()
        self._image_tmp_path = tmp.name

        # Refresh availability of OCR suggestion button for the new image.
        self.suggest_button.configure(
            state="normal" if self.app.captcha_service.ocr_available() else "disabled"
        )

        # If OCR-assisted mode was chosen (either on the Home screen
        # upfront, or via the segmented control here), automatically
        # run the suggestion as soon as the image is ready - the user
        # doesn't have to click Suggest separately. It still only fills
        # the text box; Submit remains a separate, explicit click.
        if self._mode == CaptchaMode.OCR_ASSISTED and self.app.captcha_service.ocr_available():
            self._suggest_with_ocr()

    # ------------------------------------------------------------------
    # Mode switching
    # ------------------------------------------------------------------

    def _on_mode_changed(self, value: str) -> None:
        self._mode = CaptchaMode.OCR_ASSISTED if value == "OCR-assisted" else CaptchaMode.MANUAL
        if self._mode == CaptchaMode.OCR_ASSISTED:
            if not self.app.captcha_service.ocr_available():
                self.app.show_error(
                    "KevinOCR not available",
                    "KevinOCR isn't set up yet. Go to Settings and point it at your "
                    "KevinOCR folder, or keep using manual entry.",
                )
                self.mode_switch.set("Manual")
                self._mode = CaptchaMode.MANUAL
                return
            self.suggest_button.grid()
        else:
            self.suggest_button.grid_remove()

    def _suggest_with_ocr(self) -> None:
        if not self._image_tmp_path:
            return
        self.suggest_button.configure(state="disabled", text="Reading...")
        threading.Thread(target=self._ocr_worker, daemon=True).start()

    def _ocr_worker(self) -> None:
        suggestion = self.app.captcha_service.suggest_text(self._image_tmp_path)
        self.after(0, self._apply_ocr_suggestion, suggestion)

    def _apply_ocr_suggestion(self, suggestion) -> None:
        self.suggest_button.configure(state="normal", text="\u2728  Suggest with KevinOCR")
        if suggestion:
            self.captcha_entry.delete(0, "end")
            self.captcha_entry.insert(0, suggestion)
            self.status_label.configure(
                text="OCR suggestion filled in - please check it before submitting."
            )
        else:
            self.status_label.configure(
                text="OCR couldn't read this image - please type it manually."
            )

    # ------------------------------------------------------------------
    # Submit - always an explicit user action, regardless of mode
    # ------------------------------------------------------------------

    def _submit(self) -> None:
        captcha_text = self.captcha_entry.get().strip()
        if not captcha_text:
            self.app.show_error("Missing CAPTCHA", "Please enter the CAPTCHA text.")
            return

        self.submit_button.configure(state="disabled", text="Searching...")
        self.status_label.configure(text="")
        threading.Thread(target=self._submit_worker, args=(captcha_text,), daemon=True).start()

    def _submit_worker(self, captcha_text: str) -> None:
        pending = self.app.pending_search
        search_type: SearchType = pending.get("type")
        params: dict = pending.get("params", {})

        try:
            if search_type == SearchType.CNR:
                case = self.app.search_service.search_cnr(
                    params["cnr_number"], captcha_text
                )
                results = [case]
            elif search_type == SearchType.ADVOCATE:
                results = self.app.search_service.search_advocate(
                    params["advocate_name"], captcha_text,
                    params["state_code"], params["dist_code"], params["court_complex_code"],
                    case_status=params.get("case_status", "Pending"),
                )
            elif search_type == SearchType.CASE_NUMBER:
                results = self.app.search_service.search_case_number(
                    params["case_type"], params["case_number"], params["case_year"],
                    captcha_text, params["state_code"], params["dist_code"],
                    params["court_complex_code"],
                    case_status=params.get("case_status", "Pending"),
                )
            else:
                raise ValueError(f"Unknown search type: {search_type}")
        except Exception as exc:
            logger.exception("Search submission failed.")
            self.after(0, self._on_submit_error, str(exc))
            return

        if not results:
            self.after(0, self._on_no_results)
            return

        # Hand off to Results immediately - the advocate sees the case
        # list right away instead of staring at a save progress bar.
        # Fetching each case's full detail (CNR/stage/next hearing) and
        # saving it happens in the background, driven by the Results
        # screen itself (see ResultsScreen._start_background_enrichment),
        # with rows filling in progressively as each one finishes.
        self.after(0, self._on_search_success, results)

    def _on_submit_error(self, message: str) -> None:
        self.submit_button.configure(state="normal", text="Submit")
        self.app.show_error("Search failed", message)
        # A fresh CAPTCHA is required after a failed attempt on most
        # portals (the old one is invalidated server-side either way).
        self._refresh_captcha()

    def _on_no_results(self) -> None:
        self.submit_button.configure(state="normal", text="Submit")
        self.app.show_error("No results", "No cases were found for that search.")

    def _on_search_success(self, results: list) -> None:
        self.submit_button.configure(state="normal", text="Submit")
        self.status_label.configure(text="")
        self.app.show_results(results, needs_enrichment=True)
