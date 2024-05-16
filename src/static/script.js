var return_to_top = document.getElementById("return-to-top");
var radarr_get_movies_button = document.getElementById('radarr-get-movies-button');
var start_stop_button = document.getElementById('start-stop-button');
var radarr_status = document.getElementById('radarr-status');
var radarr_spinner = document.getElementById('radarr-spinner');
var radarr_item_list = document.getElementById("radarr-item-list");
var radarr_select_all_checkbox = document.getElementById("radarr-select-all");
var radarr_select_all_container = document.getElementById("radarr-select-all-container");
var config_modal = document.getElementById('config-modal');
var radarr_sidebar = document.getElementById('radarr-sidebar');
var save_message = document.getElementById("save-message");
var save_changes_button = document.getElementById("save-changes-button");
const radarr_address = document.getElementById("radarr-address");
const radarr_api_key = document.getElementById("radarr-api-key");
const root_folder_path = document.getElementById("root-folder-path");
const tmdb_api_key = document.getElementById("tmdb-api-key");
var radarr_items = [];
var socket = io();

function check_if_all_selected() {
    var checkboxes = document.querySelectorAll('input[name="radarr-item"]');
    var all_checked = true;
    for (var i = 0; i < checkboxes.length; i++) {
        if (!checkboxes[i].checked) {
            all_checked = false;
            break;
        }
    }
    radarr_select_all_checkbox.checked = all_checked;
}

function load_radarr_data(response) {
    var every_check_box = document.querySelectorAll('input[name="radarr-item"]');
    if (response.Running) {
        start_stop_button.classList.remove('btn-success');
        start_stop_button.classList.add('btn-warning');
        start_stop_button.textContent = "Stop";
        every_check_box.forEach(item => {
            item.disabled = true;
        });
        radarr_select_all_checkbox.disabled = true;
        radarr_get_movies_button.disabled = true;
    } else {
        start_stop_button.classList.add('btn-success');
        start_stop_button.classList.remove('btn-warning');
        start_stop_button.textContent = "Start";
        every_check_box.forEach(item => {
            item.disabled = false;
        });
        radarr_select_all_checkbox.disabled = false;
        radarr_get_movies_button.disabled = false;
    }
    check_if_all_selected();
}

function append_movies(movies) {
    var movie_row = document.getElementById('movie-row');
    var template = document.getElementById('movie-template');
    movies.forEach(function (movie) {
        var clone = document.importNode(template.content, true);
        var movie_col = clone.querySelector('#movie-column');

        movie_col.querySelector('.card-title').textContent = `${movie.Name} (${movie.Year})`;
        movie_col.querySelector('.genre').textContent = movie.Genre;
        if (movie.Img_Link) {
            movie_col.querySelector('.card-img-top').src = movie.Img_Link;
            movie_col.querySelector('.card-img-top').alt = movie.Name;
        } else {
            movie_col.querySelector('.movie-img-container').removeChild(movie_col.querySelector('.card-img-top'));
        }
        movie_col.querySelector('.add-to-radarr-btn').addEventListener('click', function () {
            var add_button = this;
            add_button.disabled = true;
            add_to_radarr(movie.Name, movie.Year);
        });
        movie_col.querySelector('.get-overview-btn').addEventListener('click', function () {
            overview_req(movie);
        });
        movie_col.querySelector('.votes').textContent = movie.Votes;
        movie_col.querySelector('.rating').textContent = movie.Rating;

        var add_button = movie_col.querySelector('.add-to-radarr-btn');
        if (movie.Status === "Added" || movie.Status === "Already in Radarr") {
            movie_col.querySelector('.card-body').classList.add('status-green');
            add_button.classList.remove('btn-primary');
            add_button.classList.add('btn-secondary');
            add_button.disabled = true;
            add_button.textContent = movie.Status;
        } else if (movie.Status === "Failed to Add" || movie.Status === "Invalid Path" || movie.Status === "Invalid Movie ID") {
            movie_col.querySelector('.card-body').classList.add('status-red');
            add_button.classList.remove('btn-primary');
            add_button.classList.add('btn-danger');
            add_button.disabled = true;
            add_button.textContent = movie.Status;
        } else {
            movie_col.querySelector('.card-body').classList.add('status-blue');
        }
        movie_row.appendChild(clone);
    });
}

function add_to_radarr(movie_name, movie_year) {
    if (socket.connected) {
        socket.emit('adder', [encodeURIComponent(movie_name), movie_year]);
    }
    else {
        movie_toast("Connection Lost", "Please reload to continue.");
    }
}

function movie_toast(header, message) {
    var toast_container = document.querySelector('.toast-container');
    var toast_template = document.getElementById('toast-template').cloneNode(true);
    toast_template.classList.remove('d-none');

    toast_template.querySelector('.toast-header strong').textContent = header;
    toast_template.querySelector('.toast-body').textContent = message;
    toast_template.querySelector('.text-muted').textContent = new Date().toLocaleString();

    toast_container.appendChild(toast_template);
    var toast = new bootstrap.Toast(toast_template);
    toast.show();
    toast_template.addEventListener('hidden.bs.toast', function () {
        toast_template.remove();
    });
}

return_to_top.addEventListener("click", function () {
    window.scrollTo({ top: 0, behavior: "smooth" });
});

radarr_select_all_checkbox.addEventListener("change", function () {
    var is_checked = this.checked;
    var checkboxes = document.querySelectorAll('input[name="radarr-item"]');
    checkboxes.forEach(function (checkbox) {
        checkbox.checked = is_checked;
    });
});

radarr_get_movies_button.addEventListener('click', function () {
    radarr_get_movies_button.disabled = true;
    radarr_spinner.classList.remove('d-none');
    radarr_status.textContent = "Accessing Radarr API";
    radarr_item_list.innerHTML = '';
    socket.emit("get_radarr_movies");
});

start_stop_button.addEventListener('click', function () {
    var running_state = start_stop_button.textContent.trim() === "Start" ? true : false;
    if (running_state) {
        start_stop_button.classList.remove('btn-success');
        start_stop_button.classList.add('btn-warning');
        start_stop_button.textContent = "Stop";
        var checked_items = Array.from(document.querySelectorAll('input[name="radarr-item"]:checked'))
            .map(item => item.value);
        document.querySelectorAll('input[name="radarr-item"]').forEach(item => {
            item.disabled = true;
        });
        radarr_get_movies_button.disabled = true;
        radarr_select_all_checkbox.disabled = true;
        socket.emit("start_req", checked_items);
        if (checked_items.length > 0) {
            movie_toast("Loading new movies");
        }
    }
    else {
        start_stop_button.classList.add('btn-success');
        start_stop_button.classList.remove('btn-warning');
        start_stop_button.textContent = "Start";
        document.querySelectorAll('input[name="radarr-item"]').forEach(item => {
            item.disabled = false;
        });
        radarr_get_movies_button.disabled = false;
        radarr_select_all_checkbox.disabled = false;
        socket.emit("stop_req");
    }
});

save_changes_button.addEventListener("click", () => {
    socket.emit("update_settings", {
        "radarr_address": radarr_address.value,
        "radarr_api_key": radarr_api_key.value,
        "root_folder_path": root_folder_path.value,
        "tmdb_api_key": tmdb_api_key.value,
    });
    save_message.style.display = "block";
    setTimeout(function () {
        save_message.style.display = "none";
    }, 1000);
});

config_modal.addEventListener('show.bs.modal', function (event) {
    socket.emit("load_settings");

    function handle_settings_loaded(settings) {
        radarr_address.value = settings.radarr_address;
        radarr_api_key.value = settings.radarr_api_key;
        root_folder_path.value = settings.root_folder_path;
        tmdb_api_key.value = settings.tmdb_api_key;
        socket.off("settings_loaded", handle_settings_loaded);
    }
    socket.on("settings_loaded", handle_settings_loaded);
});

radarr_sidebar.addEventListener('show.bs.offcanvas', function (event) {
    socket.emit("side_bar_opened");
});

window.addEventListener('scroll', function () {
    if (window.innerHeight + window.scrollY >= document.body.offsetHeight) {
        socket.emit('load_more_movies');
    }
});

window.addEventListener('touchmove', function () {
    if (window.innerHeight + window.scrollY >= document.body.offsetHeight) {
        socket.emit('load_more_movies');
    }
});

window.addEventListener('touchend', () => {
    const { scrollHeight, scrollTop, clientHeight } = document.documentElement;
    if (Math.abs(scrollHeight - clientHeight - scrollTop) < 1) {
        socket.emit('load_more_movies');
    }
});

socket.on("radarr_sidebar_update", (response) => {
    if (response.Status == "Success") {
        radarr_status.textContent = "Radarr List Retrieved";
        radarr_items = response.Data;
        radarr_item_list.innerHTML = '';
        radarr_select_all_container.classList.remove('d-none');

        for (var i = 0; i < radarr_items.length; i++) {
            var item = radarr_items[i];

            var div = document.createElement("div");
            div.className = "form-check";

            var input = document.createElement("input");
            input.type = "checkbox";
            input.className = "form-check-input";
            input.id = "radarr-" + i;
            input.name = "radarr-item";
            input.value = item.name;

            if (item.checked) {
                input.checked = true;
            }

            var label = document.createElement("label");
            label.className = "form-check-label";
            label.htmlFor = "radarr-" + i;
            label.textContent = item.name;

            input.addEventListener("change", function () {
                check_if_all_selected();
            });

            div.appendChild(input);
            div.appendChild(label);

            radarr_item_list.appendChild(div);
        }
    }
    else {
        radarr_status.textContent = response.Code;
    }
    radarr_get_movies_button.disabled = false;
    radarr_spinner.classList.add('d-none');
    load_radarr_data(response);
});

socket.on("refresh_movie", (movie) => {
    var movie_cards = document.querySelectorAll('#movie-column');
    movie_cards.forEach(function (card) {
        var card_body = card.querySelector('.card-body');
        var card_movie_name = card_body.querySelector('.card-title').textContent.trim();
        card_movie_name = card_movie_name.replace(/\s*\(\d{4}\)$/, "");
        if (card_movie_name === movie.Name) {
            card_body.classList.remove('status-green', 'status-red', 'status-blue');

            var add_button = card_body.querySelector('.add-to-radarr-btn');

            if (movie.Status === "Added" || movie.Status === "Already in Radarr") {
                card_body.classList.add('status-green');
                add_button.classList.remove('btn-primary');
                add_button.classList.add('btn-secondary');
                add_button.disabled = true;
                add_button.textContent = movie.Status;
            } else if (movie.Status === "Failed to Add" || movie.Status === "Invalid Path") {
                card_body.classList.add('status-red');
                add_button.classList.remove('btn-primary');
                add_button.classList.add('btn-danger');
                add_button.disabled = true;
                add_button.textContent = movie.Status;
            } else {
                card_body.classList.add('status-blue');
                add_button.disabled = false;
            }
            return;
        }
    });
});

socket.on('more_movies_loaded', function (data) {
    append_movies(data);
});

socket.on('clear', function () {
    var movie_row = document.getElementById('movie-row');
    var movie_cards = movie_row.querySelectorAll('#movie-column');
    movie_cards.forEach(function (card) {
        card.remove();
    });
});

socket.on("new_toast_msg", function (data) {
    movie_toast(data.title, data.message);
});

socket.on("disconnect", function () {
    movie_toast("Connection Lost", "Please reconnect to continue.");
});

let overview_request_flag = false;

function overview_req(movie) {
    if (!overview_request_flag) {
        overview_request_flag = true;
        movie_overview_modal(movie);
        setTimeout(() => {
            overview_request_flag = false;
        }, 1500);
    }
}

function movie_overview_modal(movie) {
    const scrollbar_width = window.innerWidth - document.documentElement.clientWidth;
    document.body.style.overflow = 'hidden';
    document.body.style.paddingRight = `${scrollbar_width}px`;

    var modal_title = document.getElementById('overview-modal-title');
    var modal_body = document.getElementById('modal-body');

    modal_title.textContent = movie.Name;
    modal_body.innerHTML = `${movie.Overview}<br><br>Language: ${movie.Language}<br>Popularity: ${movie.Popularity}<br><br>Recommendation from: ${movie.Base_Movie}`;

    var overview_modal = new bootstrap.Modal(document.getElementById('overview-modal'));
    overview_modal.show();

    overview_modal._element.addEventListener('hidden.bs.modal', function () {
        document.body.style.overflow = 'auto';
        document.body.style.paddingRight = '0';
    });
}

const theme_switch = document.getElementById('theme-switch');
const saved_theme = localStorage.getItem('theme');
const saved_switch_position = localStorage.getItem('switch-position');

if (saved_switch_position) {
    theme_switch.checked = saved_switch_position === 'true';
}

if (saved_theme) {
    document.documentElement.setAttribute('data-bs-theme', saved_theme);
}

theme_switch.addEventListener('click', () => {
    if (document.documentElement.getAttribute('data-bs-theme') === 'dark') {
        document.documentElement.setAttribute('data-bs-theme', 'light');
    } else {
        document.documentElement.setAttribute('data-bs-theme', 'dark');
    }
    localStorage.setItem('theme', document.documentElement.getAttribute('data-bs-theme'));
    localStorage.setItem('switch_position', theme_switch.checked);
});
