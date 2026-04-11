# Notetaker — OpenWebUI Action

A OpenWebUI Action for saving chat messages into OpenWebUI Notes with optional structured metadata headings.

With one click it will:

- **Save the latest assistant message into a Note**
- **Strip model thinking and other extraneous content**
- **Append to the same Note on subsequent runs in same chat**
- **Optionally add a metadata header (Created date, Model used, Username, Prompt, Tags)**
- **Respect public/private settings and access lists**

This Action is based on the original “Save to Notes” concept by **rzhang**, available here:  
https://openwebui.com/posts/save_to_notes_21bbd23d

---

## Installation

1. Open **OpenWebUI**
2. Go to **Settings → Actions**
3. Click **Create New Action**
4. Paste the contents of `notetaker.py`
5. Save
6. Configure valves as desired:
   - Include User  
   - Include Prompt  
   - Include Timestamp  
   - Include Model  
   - Include Tags Header  
   - Default Public  
   - Access List  

The Action is now ready to use.

---

## Usage

In any chat:

1. Generate a response  
2. Click **Notetaker Icon**  
3. The assistant’s latest message is saved into a Note  
4. Re‑run the Action in the same chat to append more entries  

Notes appear under **Notes** in the sidebar.

---

## License

This project is licensed under GitHub's **Unlicense**.
