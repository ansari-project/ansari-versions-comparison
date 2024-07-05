import os
import copy
import random
import itertools
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import Json
import gradio as gr
from fastapi.responses import StreamingResponse

from agents.ansari import Ansari
from config import get_settings

# Two agents with two different system prompts
settings_1 = get_settings()
settings_1.SYSTEM_PROMPT_FILE_NAME = 'system_msg_fn_v1'
agent_1 = Ansari(settings_1)
settings_2 = get_settings()
settings_2.SYSTEM_PROMPT_FILE_NAME = 'system_msg_fn'
agent_2 = Ansari(settings_2)

text_size = gr.themes.sizes.text_md
# block_css = "block_css.css"
notice_markdown = """## Chat and Compare
- We're excited to present a comparison of two Ansari versions.
- Engage with the two anonymized versions by asking questions.
- Vote for your favorite response and continue chatting until you identify the winner.

## Let's Start!"""

# Database connection configuration
DB_CONFIG = {
    'dbname': os.getenv('AB_TESTING_DB_NAME', 'mwk'),
    'user': os.getenv('AB_TESTING_DB_USER', 'mwk'),
    'password': os.getenv('AB_TESTING_DB_PASSWORD', 'pw'),
    'host': os.getenv('AB_TESTING_DB_HOST', 'localhost'),
    'port': os.getenv('AB_TESTING_DB_PORT', '5432'),
}

# Environment variables
EXPERIMENT_ID = int(os.getenv('AB_TESTING_EXPERIMENT_ID', 1))
MODEL_1_ID = int(os.getenv('AB_TESTING_MODEL_1_ID', 1))
MODEL_2_ID = int(os.getenv('AB_TESTING_MODEL_2_ID', 2))

# Global variable to store the current model assignment
current_model_assignment = gr.State({})

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def randomly_assign_models():
    if random.choice([True, False]):
        return {'A': MODEL_1_ID, 'B': MODEL_2_ID}
    else:
        return {'A': MODEL_2_ID, 'B': MODEL_1_ID}

def insert_conversation(cursor, model_id, conversation):
    cursor.execute(
        "INSERT INTO ab_testing.ab_testing_conversations (model_id, conversation, timestamp) VALUES (%s, %s, %s) RETURNING conversation_id",
        (model_id, Json(conversation), datetime.now(timezone.utc))
    )
    return cursor.fetchone()[0]

def insert_comparison(cursor, model_a_id, model_b_id, conversation_a_id, conversation_b_id, user_vote):
    cursor.execute(
        "INSERT INTO ab_testing.ab_testing_comparisons (model_a_id, model_b_id, conversation_a_id, conversation_b_id, user_vote, timestamp) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (model_a_id, model_b_id, conversation_a_id, conversation_b_id, user_vote, datetime.now(timezone.utc))
    )

def log_vote(right_chat_history, left_chat_history, vote, current_assignment):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Insert conversations
                system_prompt_a = agent_1.sys_msg if current_assignment['A'] == MODEL_1_ID else agent_2.sys_msg
                system_prompt_b = agent_2.sys_msg if current_assignment['B'] == MODEL_2_ID else agent_1.sys_msg
                conv_a_id = insert_conversation(cur, current_assignment['A'], [system_prompt_a] + left_chat_history)
                conv_b_id = insert_conversation(cur, current_assignment['B'], [system_prompt_b] + right_chat_history)

                # Insert comparison
                insert_comparison(cur, current_assignment['A'], current_assignment['B'], conv_a_id, conv_b_id, vote)

            conn.commit()
    except psycopg2.Error as e:
        print(f"Database error: {e}")

def left_vote_last_response(right_chat_history, left_chat_history, current_assignment):
    log_vote(right_chat_history, left_chat_history, "A", current_assignment)
    return disable_buttons(4)

def right_vote_last_response(right_chat_history, left_chat_history, current_assignment):
    log_vote(right_chat_history, left_chat_history, "B", current_assignment)
    return disable_buttons(4)

def tie_vote_last_response(right_chat_history, left_chat_history, current_assignment):
    log_vote(right_chat_history, left_chat_history, "Tie", current_assignment)
    return disable_buttons(4)

def bothbad_vote_last_response(right_chat_history, left_chat_history, current_assignment):
    log_vote(right_chat_history, left_chat_history, "Both Bad", current_assignment)
    return disable_buttons(4)

def clear_conversation():
    new_assignment = randomly_assign_models()
    return (new_assignment,) + tuple([None] * 3 + [gr.Button(interactive=False, visible=True)]*6)

def gr_chat_format_to_openai_chat_format(user_message, chat_history):
    openai_chat_history = []
    for human, assistant in chat_history:
        openai_chat_history.append({"role": "user", "content": human})
        openai_chat_history.append({"role": "assistant", "content": assistant})
    openai_chat_history.append({"role": "user", "content": user_message})
    return openai_chat_history

def handle_chat(user_message, chat_history, model_id):
    agent = copy.deepcopy(agent_1 if model_id == MODEL_1_ID else agent_2)
    openai_chat_history = gr_chat_format_to_openai_chat_format(user_message, chat_history)
    return agent.replace_message_history(openai_chat_history)

def handle_user_message(user_message, right_chat_history, left_chat_history, current_assignment):
    if not user_message.strip():
        yield user_message, right_chat_history, left_chat_history, *keep_unchanged_buttons()
    else:
        right_chat_response = handle_chat(user_message, right_chat_history, current_assignment['B'])
        left_chat_response = handle_chat(user_message, left_chat_history, current_assignment['A'])

        right_chat_history.append([user_message, ""])
        left_chat_history.append([user_message, ""])

        for right_chunk, left_chunk in itertools.zip_longest(right_chat_response, left_chat_response, fillvalue=None):
            if right_chunk:
                right_content = right_chunk#.choices[0].delta.content
                if right_content:
                    right_chat_history[-1][1] += right_content
            if left_chunk:
                left_content = left_chunk#.choices[0].delta.content
                if left_content:
                    left_chat_history[-1][1] += left_content

            yield "", right_chat_history, left_chat_history, *disable_buttons()
        yield "", right_chat_history, left_chat_history, *enable_buttons()

def regenerate(right_chat_history, left_chat_history, current_assignment):
    for result in handle_user_message(right_chat_history[-1][0], right_chat_history[:-1], left_chat_history[:-1], current_assignment):
        yield result

def keep_unchanged_buttons():
    return tuple([gr.Button() for _ in range(6)])

def enable_buttons():
    return tuple([gr.Button(interactive=True, visible=True) for _ in range(6)])

def hide_buttons():
    return tuple([gr.Button(interactive=False, visible=False) for _ in range(6)])

def disable_buttons(count=6):
    return tuple([gr.Button(interactive=False, visible=True) for _ in range(count)])

def create_compare_performance_tab():
    with gr.Tab("Compare Performance", id=0):
        gr.Markdown(notice_markdown, elem_id="notice_markdown")
        with gr.Row():
            with gr.Column():
                left_chat_dialog = gr.Chatbot(
                    label="Model A",
                    elem_id="chatbot",
                    height=550,
                    show_copy_button=True,
                )
            with gr.Column():
                right_chat_dialog = gr.Chatbot(
                    label="Model B",
                    elem_id="chatbot",
                    height=550,
                    show_copy_button=True,
                )
        with gr.Row():
            leftvote_btn = gr.Button(
                value="👈  A is better", visible=False, interactive=False
            )
            rightvote_btn = gr.Button(
                value="👉  B is better", visible=False, interactive=False
            )
            tie_btn = gr.Button(value="🤝  Tie", visible=False, interactive=False)
            bothbad_btn = gr.Button(
                value="👎  Both are bad", visible=False, interactive=False
            )

        with gr.Row():
            user_msg_textbox = gr.Textbox(
                show_label=False,
                placeholder="✏️ Enter your prompt and press ENTER ⏎",
                elem_id="input_box",
            )
            send_btn = gr.Button(value="Send", variant="primary", scale=0)

        with gr.Row():
            clear_btn = gr.Button(value="🌙 New Round", interactive=False)
            regenerate_btn = gr.Button(value="🔄 Regenerate", interactive=False)
        ##
        btn_list = [
            leftvote_btn,
            rightvote_btn,
            tie_btn,
            bothbad_btn,
            regenerate_btn,
            clear_btn,
        ]
        leftvote_btn.click(
            left_vote_last_response,
            [right_chat_dialog, left_chat_dialog, current_model_assignment],
            [leftvote_btn, rightvote_btn, tie_btn, bothbad_btn],
        )
        rightvote_btn.click(
            right_vote_last_response,
            [right_chat_dialog, left_chat_dialog, current_model_assignment],
            [leftvote_btn, rightvote_btn, tie_btn, bothbad_btn],
        )
        tie_btn.click(
            tie_vote_last_response,
            [right_chat_dialog, left_chat_dialog, current_model_assignment],
            [leftvote_btn, rightvote_btn, tie_btn, bothbad_btn],
        )
        bothbad_btn.click(
            bothbad_vote_last_response,
            [right_chat_dialog, left_chat_dialog, current_model_assignment],
            [leftvote_btn, rightvote_btn, tie_btn, bothbad_btn],
        )
        clear_btn.click(
            clear_conversation,
            None,
            [current_model_assignment, user_msg_textbox, right_chat_dialog, left_chat_dialog] + btn_list,
        )

        user_msg_textbox.submit(
            handle_user_message,
            [user_msg_textbox, right_chat_dialog, left_chat_dialog, current_model_assignment],
            [user_msg_textbox, right_chat_dialog, left_chat_dialog] + btn_list,
        )

        send_btn.click(
            handle_user_message,
            [user_msg_textbox, right_chat_dialog, left_chat_dialog, current_model_assignment],
            [user_msg_textbox, right_chat_dialog, left_chat_dialog] + btn_list,
        )

        regenerate_btn.click(
            regenerate, 
            [right_chat_dialog, left_chat_dialog, current_model_assignment],
            [user_msg_textbox, right_chat_dialog, left_chat_dialog] + btn_list
        )

def create_about_tab():
    with gr.Tab("🛈 About Us", id=1):
        about_markdown = "This UI is designed to test a change to Ansari's functionality before deployment"
        gr.Markdown(about_markdown, elem_id="about_markdown")

with gr.Blocks(
    title="Ansari Compare",
    theme=gr.themes.Soft(text_size=text_size,
                          primary_hue=gr.themes.colors.sky, secondary_hue=gr.themes.colors.blue),
    #css=block_css,
) as gr_app:
    current_model_assignment = gr.State(randomly_assign_models())
    with gr.Tabs() as tabs:
        create_compare_performance_tab()
        create_about_tab()

if __name__ == "__main__":
    gr_app.queue(
            default_concurrency_limit=10,
            status_update_rate=10,
            api_open=False,
        ).launch(server_port=7860, max_threads=200, show_api=False)
