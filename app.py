from dash import Dash, dcc, html, Input, Output, State, dash_table, callback_context
import pandas as pd
import base64
import io
import dash_bootstrap_components as dbc
import phonenumbers
from dash.exceptions import PreventUpdate
import dash
import datetime
import pycountry
import os

# Update the app initialization to work with proxy servers
app = Dash(__name__, 
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    routes_pathname_prefix='/',
    requests_pathname_prefix='/'
)
app.title = "Campaign Analysis System"

# Enable suppression of callback exceptions
app.config.suppress_callback_exceptions = True

# Function to map country codes to country names
def get_country_name(phone_number):
    """Get full country name from phone number"""
    try:
        if not phone_number.startswith('+'):
            phone_number = '+' + phone_number
        parsed_number = phonenumbers.parse(phone_number, None)
        country_code = phonenumbers.region_code_for_number(parsed_number)
        
        if country_code:
            try:
                country = pycountry.countries.get(alpha_2=country_code)
                return country.name if country else country_code
            except AttributeError:
                # Handle special cases
                special_cases = {
                    'KSA': 'Saudi Arabia',
                    'UAE': 'United Arab Emirates',
                    # Add more special cases as needed
                }
                return special_cases.get(country_code, country_code)
        return "Unknown"
    except phonenumbers.phonenumberutil.NumberParseException:
        return "Unknown"

def create_product_summary_cards(df):
    """Create summary cards for auto products"""
    products = {
        'CPC': {'color': 'primary', 'pattern': 'auto.*cpc'},
        'Top Up': {'color': 'success', 'pattern': '.*top.*up.*'},  # Updated pattern
        'Gem': {'color': 'warning', 'pattern': 'auto.*gem'},
        'DT': {'color': 'danger', 'pattern': 'auto.*dt'}
    }
    
    cards = []
    for product, config in products.items():
        # Filter for the specific product
        mask = df['campaign_name'].str.lower().str.contains(
            config['pattern'], 
            regex=True, 
            na=False,
            case=False  # Added case-insensitive matching
        )
        product_data = df[mask]
        
        # Calculate metrics
        dispatched = product_data['dispatched_at'].count()
        delivered = product_data['delivered_at'].count()
        
        # Create card with percentage
        delivery_rate = (delivered / dispatched * 100) if dispatched > 0 else 0
        card = dbc.Col(
            dbc.Card([
                dbc.CardHeader(product, className=f'bg-{config["color"]} text-white fw-bold'),
                dbc.CardBody([
                    html.H4(f"Dispatched: {dispatched:,}", className='mb-2'),
                    html.H4(f"Delivered: {delivered:,}", className='mb-2'),
                    html.H6(f"Delivery Rate: {delivery_rate:.1f}%", className='text-muted')
                ])
            ], className='h-100 text-center'),
            width=3
        )
        cards.append(card)
    
    return dbc.Row(cards, className='mb-4')

# Layout of the app
app.layout = dbc.Container([
    # Header Section
    dbc.Row([
        dbc.Col(
            html.H2("Connectly Reports", className='text-center fw-bold mb-4 text-primary'),
            width=12
        )
    ]),
    
    # File Upload Section
    dbc.Row([
        dbc.Col([
            dcc.Upload(
                id='upload-data',
                children=dbc.Button("Upload CSV File", color='primary', size='lg', className='w-100'),
                multiple=False
            )
        ], width={"size": 6, "offset": 3})
    ], className='mb-4'),
    
    # Product Summary Cards
    html.Div(id='product-summary', className='mb-4'),
    
    # Filters Section
    dbc.Row([
        dbc.Col([
            html.Label("Country Filter:", className='fw-bold'),
            dcc.Dropdown(
                id='filter-country',
                options=[],
                placeholder="Select countries",
                multi=True,
                className='mb-3'
            )
        ], width=4),
        
        dbc.Col([
            html.Label("Campaign Type:", className='fw-bold'),
            dcc.Dropdown(
                id='filter-campaign-type',
                options=[
                    {'label': 'Commercial', 'value': 'Commercial'},
                    {'label': 'Non-Commercial', 'value': 'Non-Commercial'}
                ],
                placeholder="Select campaign types",
                multi=True,
                className='mb-3'
            )
        ], width=4),
        
        dbc.Col([
            html.Label("Date Range:", className='fw-bold'),
            dcc.DatePickerRange(
                id='filter-date',
                start_date=None,
                end_date=None,
                className='mb-3'
            )
        ], width=4)
    ], id='filters-container', style={'display': 'none'}),
    
    # Filter Button
    dbc.Row([
        dbc.Col([
            dbc.Button(
                "Apply Filters",
                id='filter-button',
                color='success',
                className='w-100'
            )
        ], width={"size": 4, "offset": 4})
    ], className='mb-4'),
    
    # Tabs Section
    dbc.Tabs([
        dbc.Tab(label="Data Table", tab_id="data-table-tab"),
        dbc.Tab(label="Campaign Summary", tab_id="campaign-summary-tab"),
        dbc.Tab(label="Cost Analysis", tab_id="cost-analysis-tab"),
        dbc.Tab(label="Country Analysis", tab_id="country-analysis-tab")
    ], id="tabs", active_tab="data-table-tab", className='mb-4'),
    
    # Content Display Area
    html.Div(id='tab-content')
    
], fluid=True)

# Store data globally
data = None

def process_uploaded_file(contents):
    """Process uploaded CSV file and return processed dataframe"""
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    df = pd.read_csv(io.StringIO(decoded.decode('utf-8')))

    # Updated column mapping with campaign name variations
    column_mapping = {
        'Button Clicks': 'button_clicks',
        'Delivered': 'delivered',
        'Link Clicks': 'link_clicks',
        'Read': 'read_at',
        'Sent': 'sent_at',
        'Campaign Name': 'campaign_name',  # Add potential variations
        'campaign': 'campaign_name',
        'Campaign': 'campaign_name'
    }
    
    # Apply column mapping for existing columns only
    for old_col, new_col in column_mapping.items():
        if old_col in df.columns:
            df.rename(columns={old_col: new_col}, inplace=True)
    
    # Verify campaign_name column exists
    if 'campaign_name' not in df.columns:
        # Try to find a column containing 'campaign' (case insensitive)
        campaign_cols = [col for col in df.columns if 'campaign' in col.lower()]
        if campaign_cols:
            df.rename(columns={campaign_cols[0]: 'campaign_name'}, inplace=True)
        else:
            raise ValueError("Could not find campaign name column in the CSV file")

    # Updated commercial keywords to include all variations
    commercial_keywords = [
        'cpc', 'dt', 'gem', 
        'top up', 'top_up', 'topup',
        'automation'
    ]
    
    def is_commercial_campaign(campaign_name):
        # Convert campaign name to lowercase for case-insensitive matching
        name = str(campaign_name).lower()
        # Check if any of the keywords are in the campaign name
        return any(keyword in name.replace('_', ' ') for keyword in commercial_keywords)

    # Apply the commercial classification
    df['campaign_type'] = df['campaign_name'].apply(
        lambda x: 'Commercial' if is_commercial_campaign(x) else 'Non-Commercial'
    )

    df['country_name'] = df['customer_external_id'].astype(str).apply(get_country_name)
    df['country_name'] = df['country_name'].fillna('Unknown')

    # Handle dates
    df['dispatched_at'] = pd.to_datetime(df['dispatched_at'], errors='coerce')
    df = df.dropna(subset=['dispatched_at'])
    
    return df

@app.callback(
    [Output('filters-container', 'style'),
     Output('filter-country', 'options'),
     Output('filter-date', 'start_date'),
     Output('filter-date', 'end_date'),
     Output('tab-content', 'children', allow_duplicate=True),
     Output('product-summary', 'children')],  # Add new output
    [Input('upload-data', 'contents'),
     Input('tabs', 'active_tab'),
     Input('filter-button', 'n_clicks'),
     Input('filter-country', 'value'),
     Input('filter-campaign-type', 'value'),
     Input('filter-date', 'start_date'),
     Input('filter-date', 'end_date')],
    [State('upload-data', 'filename')],
    prevent_initial_call=True
)
def update_content(contents, active_tab, n_clicks, filter_country, filter_campaign_type, 
                  start_date, end_date, filename):
    global data
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate

    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    # Handle file upload
    if trigger_id == 'upload-data':
        if contents is None:
            return {'display': 'none'}, [], None, None, html.Div("Please upload a file."), html.Div()
        try:
            df = process_uploaded_file(contents)
            data = df  # Store globally
            
            # Get filter values
            country_options = [{'label': country, 'value': country} 
                             for country in sorted(df['country_name'].unique())]
            start_date = df['dispatched_at'].min().date()
            end_date = df['dispatched_at'].max().date()
            
            return {'display': 'block'}, country_options, start_date, end_date, create_data_table(df), create_product_summary_cards(df)
        except Exception as e:
            return {'display': 'none'}, [], None, None, html.Div(f"Error: {str(e)}", className='text-danger'), html.Div()

    # Handle tab changes
    elif trigger_id == 'tabs':
        if data is None:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, html.Div("No data available."), dash.no_update
        
        if active_tab == "data-table-tab":
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, create_data_table(data), dash.no_update
        elif active_tab == "campaign-summary-tab":
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, create_summary_table(data), dash.no_update
        elif active_tab == "cost-analysis-tab":
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, create_cost_analysis_table(data), dash.no_update
        else:  # country-analysis-tab
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, create_country_analysis_table(data), dash.no_update

    # Handle filter applications
    elif trigger_id in ['filter-button', 'filter-country', 'filter-campaign-type', 'filter-date']:
        if data is None:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

        filtered_data = apply_filters(data, filter_country, filter_campaign_type, start_date, end_date)
        
        if active_tab == "data-table-tab":
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, create_data_table(filtered_data), dash.no_update
        else:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, create_summary_table(filtered_data), dash.no_update

    return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

# Helper functions to create tables
def create_data_table(df):
    return dash_table.DataTable(
        id='data-table',
        columns=[{'name': i, 'id': i} for i in df.columns],
        data=df.to_dict('records'),
        page_size=10,
        style_table={'overflowX': 'auto'},
        style_cell={'textAlign': 'left', 'padding': '10px'},
        style_header={
            'backgroundColor': '#007bff',
            'color': 'white',
            'fontWeight': 'bold',
            'textAlign': 'center'
        },
        style_data_conditional=[{
            'if': {'row_index': 'odd'},
            'backgroundColor': 'rgb(248, 248, 248)'
        }]
    )

def create_summary_table(df):
    summary_df = df.groupby('campaign_name').agg({
        'dispatched_at': 'count',
        'sent_at': 'count',
        'delivered_at': 'count',
        'read_at': 'count',
        'button_clicks': 'count',
        'link_clicks': 'count'
    }).reset_index().rename(columns={
        'dispatched_at': 'Dispatched',
        'sent_at': 'Sent',
        'delivered_at': 'Delivered',
        'read_at': 'Read',
        'button_clicks': 'Button Clicks',
        'link_clicks': 'Link Clicks'
    })
    
    return dash_table.DataTable(
        id='summary-table',
        columns=[{'name': i, 'id': i} for i in summary_df.columns],
        data=summary_df.to_dict('records'),
        page_size=10,
        style_table={'overflowX': 'auto'},
        style_cell={'textAlign': 'left', 'padding': '10px'},
        style_header={
            'backgroundColor': '#28a745',
            'color': 'white',
            'fontWeight': 'bold',
            'textAlign': 'center'
        },
        style_data_conditional=[{
            'if': {'row_index': 'odd'},
            'backgroundColor': 'rgb(248, 248, 248)'
        }]
    )

def create_cost_analysis_table(df):
    # Filter for non-commercial campaigns only
    non_commercial = df[df['campaign_type'] == 'Non-Commercial']
    
    # Calculate costs and aggregate by campaign
    cost_df = non_commercial.groupby('campaign_name').agg({
        'delivered_at': 'count',
    }).reset_index()
    
    # Add cost calculation
    cost_df['Cost (USD)'] = cost_df['delivered_at'] * 0.04
    cost_df = cost_df.rename(columns={
        'delivered_at': 'Delivered Messages',
    })
    
    # Add totals row
    totals = {
        'campaign_name': 'Total',
        'Delivered Messages': cost_df['Delivered Messages'].sum(),
        'Cost (USD)': cost_df['Cost (USD)'].sum()
    }
    cost_df = pd.concat([cost_df, pd.DataFrame([totals])], ignore_index=True)
    
    # Format cost column to show 2 decimal places
    cost_df['Cost (USD)'] = cost_df['Cost (USD)'].apply(lambda x: f"${x:.2f}")
    
    return dash_table.DataTable(
        id='cost-table',
        columns=[{'name': i, 'id': i} for i in cost_df.columns],
        data=cost_df.to_dict('records'),
        page_size=10,
        style_table={'overflowX': 'auto'},
        style_cell={'textAlign': 'left', 'padding': '10px'},
        style_header={
            'backgroundColor': '#dc3545',  # Bootstrap danger color
            'color': 'white',
            'fontWeight': 'bold',
            'textAlign': 'center'
        },
        style_data_conditional=[{
            'if': {'row_index': 'odd'},
            'backgroundColor': 'rgb(248, 248, 248)'
        },
        {
            'if': {'filter_query': '{campaign_name} = "Total"'},
            'backgroundColor': '#dc3545',
            'color': 'white',
            'fontWeight': 'bold'
        }]
    )

def create_country_analysis_table(df):
    """Create table showing metrics per country"""
    country_df = df.groupby('country_name').agg({
        'dispatched_at': 'count',
        'delivered_at': 'count',
        'read_at': 'count',
        'button_clicks': 'count',  # Changed from 'sum' to 'count'
        'link_clicks': 'count'
    }).reset_index()
    
    # Calculate delivery and read rates
    country_df['Delivery Rate'] = (country_df['delivered_at'] / country_df['dispatched_at'] * 100).round(2)
    country_df['Read Rate'] = (country_df['read_at'] / country_df['delivered_at'] * 100).round(2)
    
    # Rename columns
    country_df = country_df.rename(columns={
        'country_name': 'Country',
        'dispatched_at': 'Dispatched',
        'delivered_at': 'Delivered',
        'read_at': 'Read',
        'button_clicks': 'Button Clicks',
        'link_clicks': 'Link Clicks'
    })
    
    # Add % symbol to rate columns
    country_df['Delivery Rate'] = country_df['Delivery Rate'].apply(lambda x: f"{x}%")
    country_df['Read Rate'] = country_df['Read Rate'].apply(lambda x: f"{x}%")
    
    # Sort by dispatched messages descending
    country_df = country_df.sort_values('Dispatched', ascending=False)
    
    return dash_table.DataTable(
        id='country-table',
        columns=[{'name': i, 'id': i} for i in country_df.columns],
        data=country_df.to_dict('records'),
        page_size=10,
        style_table={'overflowX': 'auto'},
        style_cell={'textAlign': 'left', 'padding': '10px'},
        style_header={
            'backgroundColor': '#17a2b8',  # Bootstrap info color
            'color': 'white',
            'fontWeight': 'bold',
            'textAlign': 'center'
        },
        style_data_conditional=[{
            'if': {'row_index': 'odd'},
            'backgroundColor': 'rgb(248, 248, 248)'
        }]
    )

def apply_filters(df, filter_country, filter_campaign_type, start_date, end_date):
    filtered_data = df.copy()
    
    if filter_country and len(filter_country) > 0:
        filtered_data = filtered_data[filtered_data['country_name'].isin(filter_country)]
    if filter_campaign_type and len(filter_campaign_type) > 0:
        filtered_data = filtered_data[filtered_data['campaign_type'].isin(filter_campaign_type)]
    if start_date and end_date:
        filtered_data = filtered_data[
            (filtered_data['dispatched_at'].dt.date >= pd.to_datetime(start_date).date()) & 
            (filtered_data['dispatched_at'].dt.date <= pd.to_datetime(end_date).date())
        ]
    
    return filtered_data

def handle_upload_and_tabs(contents, active_tab, filename):
    global data
    ctx = callback_context

    if not ctx.triggered:
        raise PreventUpdate

    trigger = ctx.triggered[0]['prop_id'].split('.')[0]

    if trigger == 'upload-data':
        if contents is None:
            return {'display': 'none'}, [], None, None, html.Div("Please upload a file to begin analysis.", className='text-center')

        try:
            # Decode and read the uploaded file
            content_type, content_string = contents.split(',')
            decoded = base64.b64decode(content_string)
            df = pd.read_csv(io.StringIO(decoded.decode('utf-8')))

            # Column mapping
            column_mapping = {
                'Button Clicks': 'button_clicks',
                'Delivered': 'delivered',
                'Link Clicks': 'link_clicks',
                'Read': 'read_at',
                'Sent': 'sent_at'
            }
            df.rename(columns=column_mapping, inplace=True)

            # Add derived fields
            df['campaign_type'] = df['campaign_name'].apply(
                lambda x: 'Commercial' if any(keyword in x.lower() for keyword in ['cps', 'top up', 'gems', 'dt']) else 'Non-Commercial'
            )
            df['country_name'] = df['customer_external_id'].astype(str).apply(get_country_name)
            df['country_name'] = df['country_name'].fillna('Unknown')

            # Handle dates
            df['dispatched_at'] = pd.to_datetime(df['dispatched_at'], errors='coerce')
            df = df.dropna(subset=['dispatched_at'])
            
            # Get date range for filter
            start_date = df['dispatched_at'].min().date() if not df['dispatched_at'].isna().all() else None
            end_date = df['dispatched_at'].max().date() if not df['dispatched_at'].isna().all() else None

            # Store data globally
            data = df

            country_options = [{'label': country, 'value': country} 
                             for country in sorted(df['country_name'].unique())]
            
            # Initial data table
            table = dash_table.DataTable(
                id='data-table',
                columns=[{'name': i, 'id': i} for i in df.columns],
                data=df.to_dict('records'),
                page_size=10,
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'left', 'padding': '10px'},
                style_header={
                    'backgroundColor': '#007bff',
                    'color': 'white',
                    'fontWeight': 'bold',
                    'textAlign': 'center'
                },
                style_data_conditional=[{
                    'if': {'row_index': 'odd'},
                    'backgroundColor': 'rgb(248, 248, 248)'
                }]
            )

            return {'display': 'block'}, country_options, start_date, end_date, table

        except Exception as e:
            error_message = html.Div([
                html.H4("Error Processing File", className='text-danger'),
                html.P(f"Details: {str(e)}")
            ], className='text-center')
            return {'display': 'none'}, [], None, None, error_message

    elif trigger == 'tabs':
        if data is None:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, html.Div("No data available. Please upload a file.", className='text-center')

        if active_tab == "data-table-tab":
            table = dash_table.DataTable(
                id='data-table',
                columns=[{'name': i, 'id': i} for i in data.columns],
                data=data.to_dict('records'),
                page_size=10,
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'left', 'padding': '10px'},
                style_header={
                    'backgroundColor': '#007bff',
                    'color': 'white',
                    'fontWeight': 'bold',
                    'textAlign': 'center'
                },
                style_data_conditional=[{
                    'if': {'row_index': 'odd'},
                    'backgroundColor': 'rgb(248, 248, 248)'
                }]
            )
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, table

        elif active_tab == "campaign-summary-tab":
            required_columns = [
                'campaign_name', 'dispatched_at', 'sent_at', 'delivered_at',
                'read_at', 'button_clicks', 'link_clicks'
            ]
            
            missing_columns = [col for col in required_columns if col not in data.columns]
            if missing_columns:
                return dash.no_update, dash.no_update, dash.no_update, dash.no_update, html.Div(
                    f"Missing columns: {', '.join(missing_columns)}",
                    className='text-danger text-center'
                )

            summary_df = data.groupby('campaign_name').agg({
                'dispatched_at': 'count',
                'sent_at': 'count',
                'delivered_at': 'count',
                'read_at': 'count',
                'button_clicks': 'count',
                'link_clicks': 'count'
            }).reset_index().rename(columns={
                'dispatched_at': 'Dispatched',
                'sent_at': 'Sent',
                'delivered_at': 'Delivered',
                'read_at': 'Read',
                'button_clicks': 'Button Clicks',
                'link_clicks': 'Link Clicks'
            })

            summary_table = dash_table.DataTable(
                id='summary-table',
                columns=[{'name': i, 'id': i} for i in summary_df.columns],
                data=summary_df.to_dict('records'),
                page_size=10,
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'left', 'padding': '10px'},
                style_header={
                    'backgroundColor': '#28a745',
                    'color': 'white',
                    'fontWeight': 'bold',
                    'textAlign': 'center'
                },
                style_data_conditional=[{
                    'if': {'row_index': 'odd'},
                    'backgroundColor': 'rgb(248, 248, 248)'
                }]
            )
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, summary_table

    raise PreventUpdate

# Run the app
if __name__ == '__main__':
    app.run_server(debug=True, host='0.0.0.0', port=8050)