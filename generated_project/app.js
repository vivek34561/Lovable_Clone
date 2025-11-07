// Main application logic for managing tasks

// Get DOM elements
const taskInput = document.getElementById('new-task-input');
const addTaskButton = document.getElementById('add-task-button');
const taskList = document.getElementById('task-list');
const filterButtons = document.querySelectorAll('.filter-button');

let tasks = []; // Array to hold tasks
let currentFilter = 'all'; // Current filter state

// Function to render tasks based on the current filter
function renderTasks() {
    // Clear the task list
    taskList.innerHTML = '';

    // Filter tasks based on the current filter
    const filteredTasks = tasks.filter(task => {
        if (currentFilter === 'completed') return task.completed;
        if (currentFilter === 'pending') return !task.completed;
        return true; // 'all'
    });

    // Create task elements
    filteredTasks.forEach((task, index) => {
        const li = document.createElement('li');
        li.textContent = task.text;
        li.classList.toggle('completed', task.completed);

        // Add event listener for marking task as completed
        li.addEventListener('click', () => markTaskCompleted(index));

        // Create delete button
        const deleteButton = document.createElement('button');
        deleteButton.textContent = 'Delete';
        deleteButton.classList.add('delete-button');
        deleteButton.addEventListener('click', (e) => {
            e.stopPropagation(); // Prevent triggering the li click event
            deleteTask(index);
        });

        li.appendChild(deleteButton);
        taskList.appendChild(li);
    });
}

// Function to add a new task
function addTask() {
    const taskText = taskInput.value.trim();
    if (taskText === '') return; // Do nothing if input is empty

    tasks.push({ text: taskText, completed: false });
    taskInput.value = ''; // Clear the input field
    renderTasks();
}

// Function to mark a task as completed
function markTaskCompleted(index) {
    tasks[index].completed = !tasks[index].completed;
    renderTasks();
}

// Function to delete a task
function deleteTask(index) {
    tasks.splice(index, 1);
    renderTasks();
}

// Function to filter tasks
function filterTasks(filter) {
    currentFilter = filter;
    renderTasks();
}

// Add event listeners
addTaskButton.addEventListener('click', addTask);
taskInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') addTask();
});

filterButtons.forEach(button => {
    button.addEventListener('click', () => {
        filterTasks(button.id.replace('filter-', ''));
    });
});

// Initial render
renderTasks();